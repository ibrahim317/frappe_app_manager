frappe.listview_settings["Frappe Custom App"] = {
get_indicator: function (doc) {
		if (doc.status === "Installed") {
			return [__("Installed"), "green", "status,=,Installed"];
		} else if (doc.status === "Available") {
			return [__("Available"), "grey", "status,=,Available"];
		}
    },
	onload(listview) {
		// Remove the "Reload List" button using jQuery
		$('[data-original-title="Reload List"]').remove();
		$('.layout-side-section.right').remove();
		
		
		listview.page.add_inner_button(__("Get Application"), () => {
			const d = new frappe.ui.Dialog({
				title: __("Get Application"),
				fields: [
					{
						label: __("Repository URL"),
						fieldname: "repo_url",
						fieldtype: "Data",
						reqd: 1,
						placeholder: __("https://github.com/<github-user>/<repo>"),
						desc: __("Enter the full repository URL (e.g. https://github.com/frappe/erpnext or git@github.com:frappe/erpnext.git)"),
					},
					{
						label: __("Private Repository"),
						fieldname: "is_private",
						fieldtype: "Check",
						default: 0,
					},
					{
						label: __("Username"),
						fieldname: "username",
						fieldtype: "Data",
						depends_on: "is_private",
						placeholder: __("GitHub username"),
					},
					{
						label: __("Personal Access Token (PAT)"),
						fieldname: "pat",
						fieldtype: "Password",
						depends_on: "is_private",
						placeholder: __("GitHub Personal Access Token"),
					},
				],
				primary_action_label: __("Get App"),
				primary_action: function () {
					const values = d.get_values();
					if (!values) return;

					// Validate private repo fields if enabled
					if (values.is_private) {
						if (!values.username || !values.pat) {
							frappe.msgprint({
								title: __("Validation Error"),
								message: __("Username and Personal Access Token are required for private repositories."),
								indicator: "red",
							});
							return;
						}
					}

					// Prepare arguments for API calls
					const api_args = { 
						repo_url: values.repo_url,
						is_private: values.is_private || false,
						username: values.username || '',
						pat: values.pat || ''
					};

					// First check if app already exists
					frappe.call({
						method: "app_manager.api.apps.check_app_exists",
						args: api_args,
						freeze: true,
						freeze_message: __("Checking if app exists..."),
					}).then((r) => {
						const result = r?.message || {};
						
						if (result.exists) {
							// App exists, show confirmation dialog
							const confirm_dialog = new frappe.ui.Dialog({
								title: __("App Already Exists"),
								fields: [
									{
										fieldtype: "HTML",
										fieldname: "message",
										options: `<div class="alert alert-info">
											<p>${__("App '{0}' already exists. Do you want to update it?", [result.app_name])}</p>
										</div>`
									}
								],
								primary_action_label: __("Update"),
								secondary_action_label: __("Cancel"),
								primary_action: function() {
									confirm_dialog.hide();
									// Call get_app with overwrite flag (now runs in background)
									frappe.call({
										method: "app_manager.api.apps.get_app",
										args: { ...api_args, overwrite: true },
										freeze: false, // No freeze since it's a background job
									}).then((r) => {
										const msg = r?.message || {};
										if (msg.ok) {
											frappe.show_alert({
												message: msg.message,
												indicator: "blue"
											}, 8);
										}
										d.hide();
									}).catch((e) => {
										frappe.show_alert({
											message: __("Failed to start app update."),
											indicator: "red"
										}, 10);
									});
								},
								secondary_action: function() {
									confirm_dialog.hide();
								}
							});
							confirm_dialog.show();
						} else {
							// App doesn't exist, proceed with normal get_app (now runs in background)
							frappe.call({
								method: "app_manager.api.apps.get_app",
								args: api_args,
								freeze: false, // No freeze since it's a background job
							}).then((r) => {
								const msg = r?.message || {};
								if (msg.ok) {
									frappe.show_alert({
										message: msg.message,
										indicator: "blue"
									}, 8);
								}
								d.hide();
							}).catch((e) => {
								frappe.show_alert({
									message: __("Failed to start app fetch."),
									indicator: "red"
								}, 10);
							});
						}
					}).catch((e) => {
						frappe.msgprint({
							title: __("Error"),
							message: __("Failed to check if app exists."),
							indicator: "red",
						});
					});
				},
			});

			d.show();
		});

		listview.page.add_inner_button(__("Reload Apps"), () => {
			frappe.call({
				method: "app_manager.api.apps.reload_apps",
				args: {},
				freeze: true,
				freeze_message: __("Reloading apps..."),
			}).then((r) => {
				const msg = r?.message || {};
				frappe.msgprint({
					title: __("Reload Complete"),
					message: __("Apps reloaded."),
					indicator: "green",
				});
				listview.refresh();
			}).catch(() => {
				frappe.msgprint({
					title: __("Error"),
					message: __("Failed to reload apps."),
					indicator: "red",
				});
			});
		});
	},
};


