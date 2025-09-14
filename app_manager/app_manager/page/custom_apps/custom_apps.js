frappe.pages["custom-apps"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Custom Apps"),
		single_column: true,
	});
};

frappe.pages["custom-apps"].on_page_show = function (wrapper) {
	load_desk_page(wrapper);
};

function load_desk_page(wrapper) {
	let $parent = $(wrapper).find(".layout-main-section");
	$parent.empty();

	frappe.require("custom_apps.bundle.jsx").then(() => {
		frappe.custom_apps = new frappe.ui.CustomApps({
			wrapper: $parent,
			page: wrapper.page,
		});
	});
}