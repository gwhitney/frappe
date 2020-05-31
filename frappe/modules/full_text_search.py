# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt

from __future__ import unicode_literals
import frappe
import os
from whoosh.index import create_in, open_dir
from whoosh.fields import TEXT, ID, Schema
from whoosh.qparser import MultifieldParser, FieldsPlugin, WildcardPlugin
from bs4 import BeautifulSoup
from frappe.website.render import render_page
from frappe.utils import set_request, cint
from frappe.utils.global_search import get_routes_to_index


def build_index_for_all_routes():
	print("Building search index for all web routes...")
	routes = get_routes_to_index()
	documents = [get_document_to_index(route) for route in routes]
	build_index("web_routes", documents)


def get_document_to_index(route):
	frappe.set_user("Guest")
	frappe.local.no_cache = True

	try:
		set_request(method="GET", path=route)
		content = render_page(route)
		soup = BeautifulSoup(content, "html.parser")
		page_content = soup.find(class_="page_content")
		text_content = page_content.text if page_content else ""
		title = soup.title.text.strip() if soup.title else route

		frappe.set_user("Administrator")

		return frappe._dict(title=title, content=text_content, path=route)
	except (
		frappe.PermissionError,
		frappe.DoesNotExistError,
		frappe.ValidationError,
		Exception,
	):
		pass


def build_index(index_name, documents):
	schema = Schema(
		title=TEXT(stored=True), path=ID(stored=True), content=TEXT(stored=True)
	)

	index_dir = os.path.join(frappe.utils.get_bench_path(), "indexes", index_name)
	frappe.create_folder(index_dir)

	ix = create_in(index_dir, schema)
	writer = ix.writer()

	for document in documents:
		if document:
			writer.add_document(
				title=document.title, path=document.path, content=document.content
			)

	writer.commit()


def search(index_name, text, limit=20):
	index_dir = os.path.join(frappe.utils.get_bench_path(), "indexes", index_name)
	ix = open_dir(index_dir)

	results = None
	out = []
	with ix.searcher() as searcher:
		parser = MultifieldParser(["title", "content"], ix.schema)
		parser.remove_plugin_class(FieldsPlugin)
		parser.remove_plugin_class(WildcardPlugin)
		query = parser.parse(text)

		results = searcher.search(query, limit=limit)
		for r in results:
			title_highlights = r.highlights("title")
			content_highlights = r.highlights("content")
			out.append(
				frappe._dict(
					title=r["title"],
					path=r["path"],
					title_highlights=title_highlights,
					content_highlights=content_highlights,
				)
			)

	return out


@frappe.whitelist(allow_guest=True)
def web_search(query, limit=20):
	limit = cint(limit)
	return search("web_routes", query, limit)
