app_name = "erpbio_indonesia_localization"
app_title = "ERPbio Indonesia Localization"
app_publisher = "Architect Coding"
app_description = "Indonesian tax localization (Coretax e-Faktur, PPN, PPh) for the ERPbio suite"
app_email = "jthenadi@gmail.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext"]

# Installation
# ------------
# Custom fields + seed data. Also re-run on every migrate so field updates
# ship with app updates (everything in setup_eil is idempotent).

after_install = "erpbio_indonesia_localization.setup.install.setup_eil"
after_migrate = "erpbio_indonesia_localization.setup.install.setup_eil"

# Document Events
# ---------------
# Observers only: they create/clean Bukti Potong tracking docs and never touch
# the Payment Entry itself or its GL. Both are fully try/except-guarded.

doc_events = {
	"Payment Entry": {
		"on_submit": "erpbio_indonesia_localization.doc_events.payment_entry.on_submit",
		"on_cancel": "erpbio_indonesia_localization.doc_events.payment_entry.on_cancel",
	}
}

# /erpbio-tax SPA (tax-frontend build served from www/erpbio_tax.html)
website_route_rules = [
	{"from_route": "/erpbio-tax", "to_route": "erpbio_tax"},
	{"from_route": "/erpbio-tax/<path:app_path>", "to_route": "erpbio_tax"},
]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "erpbio_indonesia_localization",
# 		"logo": "/assets/erpbio_indonesia_localization/logo.png",
# 		"title": "ERPbio Indonesia Localization",
# 		"route": "/erpbio_indonesia_localization",
# 		"has_permission": "erpbio_indonesia_localization.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/erpbio_indonesia_localization/css/erpbio_indonesia_localization.css"
# app_include_js = "/assets/erpbio_indonesia_localization/js/erpbio_indonesia_localization.js"

# include js, css files in header of web template
# web_include_css = "/assets/erpbio_indonesia_localization/css/erpbio_indonesia_localization.css"
# web_include_js = "/assets/erpbio_indonesia_localization/js/erpbio_indonesia_localization.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "erpbio_indonesia_localization/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "erpbio_indonesia_localization/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "erpbio_indonesia_localization.utils.jinja_methods",
# 	"filters": "erpbio_indonesia_localization.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "erpbio_indonesia_localization.install.before_install"
# after_install = "erpbio_indonesia_localization.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "erpbio_indonesia_localization.uninstall.before_uninstall"
# after_uninstall = "erpbio_indonesia_localization.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "erpbio_indonesia_localization.utils.before_app_install"
# after_app_install = "erpbio_indonesia_localization.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "erpbio_indonesia_localization.utils.before_app_uninstall"
# after_app_uninstall = "erpbio_indonesia_localization.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "erpbio_indonesia_localization.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "erpbio_indonesia_localization.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"erpbio_indonesia_localization.tasks.all"
# 	],
# 	"daily": [
# 		"erpbio_indonesia_localization.tasks.daily"
# 	],
# 	"hourly": [
# 		"erpbio_indonesia_localization.tasks.hourly"
# 	],
# 	"weekly": [
# 		"erpbio_indonesia_localization.tasks.weekly"
# 	],
# 	"monthly": [
# 		"erpbio_indonesia_localization.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "erpbio_indonesia_localization.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "erpbio_indonesia_localization.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "erpbio_indonesia_localization.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "erpbio_indonesia_localization.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["erpbio_indonesia_localization.utils.before_request"]
# after_request = ["erpbio_indonesia_localization.utils.after_request"]

# Job Events
# ----------
# before_job = ["erpbio_indonesia_localization.utils.before_job"]
# after_job = ["erpbio_indonesia_localization.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"erpbio_indonesia_localization.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

