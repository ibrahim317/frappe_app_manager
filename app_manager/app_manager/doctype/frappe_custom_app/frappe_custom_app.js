// Copyright (c) 2025, ibrahim317 and contributors
// For license information, please see license.txt

frappe.ui.form.on("Frappe Custom App", {
	refresh(frm) {
		frm.events.add_action_buttons(frm);
		frm.events.setup_websocket_listener(frm);
	},

	add_action_buttons(frm) {
		const status = frm.doc.status;

		if (status === "Installed") {
			frm.add_custom_button(__("Update App"), () => {
				frm.events._update_app(frm);
			}, __("Actions"));
			frm.add_custom_button(__("Uninstall App"), () => {
				frm.events._confirm_and_call(frm, {
					title: __("Please wait, while the app is being uninstalled"),
					message: __("Are you sure you want to uninstall this app from the current site?"),
					method: "app_manager.api.apps.uninstall_app",
					args: { app_name: frm.doc.app_name },
					success_indicator: "orange",
					after: () => frm.reload_doc(),
				});
			}, __("Actions"));
		}

		if (status === "Available") {
			frm.add_custom_button(__("Delete App"), () => {
				frm.events._confirm_and_call(frm, {
					title: __("Please wait, while the app is being deleted"),
					message: __("This will remove the app from bench (code and config). Continue?"),
					method: "app_manager.api.apps.remove_app",
					args: { app_name: frm.doc.app_name },
					success_indicator: "red",
				});
			}, __("Actions"));
			frm.add_custom_button(__("Install Package"), () => {
				frm.events._call_api(frm, {
					title: __("Please wait, while the app package is being installed"),
					method: "app_manager.api.apps.install_app_package",
					args: { app_name: frm.doc.app_name },
					success_indicator: "blue",
					after: () => frm.reload_doc(),
				});
			}, __("Actions"));
			frm.add_custom_button(__("Install App"), () => {
				frm.events._call_api(frm, {
					title: __("Please wait, while the app is being installed"),
					method: "app_manager.api.apps.install_app",
					args: { app_name: frm.doc.app_name },
					success_indicator: "green",
					after: () => frm.reload_doc(),
				});
			}, __("Actions"));
		}
	},
	_update_app(frm) {
		// Get the repository URL from the app
		const repo_url = frm.doc.repo_url;
		if (!repo_url) {
			frappe.msgprint({
				title: __("Error"),
				message: __("Repository URL not found for this app."),
				indicator: "red",
			});
			return;
		}

		// Show confirmation dialog
		frappe.confirm(
			__("Are you sure you want to update '{0}'? This will fetch the latest version from the repository.", [frm.doc.app_name]),
			() => {
				// Call get_app with overwrite flag (runs in background)
				frappe.call({
					method: "app_manager.api.apps.get_app",
					args: { repo_url: repo_url, overwrite: true },
					freeze: false, // No freeze since it's a background job
				}).then((r) => {
					const msg = r?.message || {};
					if (msg.ok) {
						frappe.show_alert({
							message: msg.message,
							indicator: "blue"
						}, 8);
					}
				}).catch((e) => {
					frappe.show_alert({
						message: __("Failed to start app update."),
						indicator: "red"
					}, 10);
				});
			},
			() => {}
		);
	},

	_confirm_and_call(frm, opts) {
		frappe.confirm(
			opts.message,
			() => frm.events._call_api(frm, opts),
			() => {}
		);
	},

	_call_api(frm, opts) {
		frappe.call({
			method: opts.method,
			args: opts.args || {},
			freeze: true,
			freeze_message: opts.title || __("Please wait..."),
		}).then((r) => {
			const msg = r?.message || {};
			const stdout = msg.stdout || "";
			const stderr = msg.stderr || "";
			const ok = Boolean(msg.ok);
			frappe.msgprint({
				title: ok ? opts.title || __("Success") : __("Completed with Warnings/Errors"),
				message: `<pre style="white-space: pre-wrap;">${frappe.utils.escape_html(stdout || stderr || __("No output"))}</pre>`,
				indicator: ok ? (opts.success_indicator || "green") : "orange",
			});
			// On successful removal, go back to list since doc is deleted
			if (ok && opts.method === "app_manager.api.apps.remove_app") {
				frappe.set_route("List", "Frappe Custom App");
				return;
			}
			// Update status locally on success without full reload
			if (ok) {
				if (opts.method === "app_manager.api.apps.install_app") {
					frm.doc.status = "Installed";
				} else if (
					opts.method === "app_manager.api.apps.uninstall_app" ||
					opts.method === "app_manager.api.apps.remove_app"
				) {
					frm.doc.status = "Available";
				}
				frm.refresh_fields(["status"]);
				frm.page.clear_inner_toolbar();
				frm.events.add_action_buttons(frm);
			}
			if (typeof opts.after === "function") {
				opts.after();
			}
		}).catch((err) => {
			frappe.msgprint({
				title: __("Error"),
				message: __("Operation failed."),
				indicator: "red",
			});
		});
	},
});
