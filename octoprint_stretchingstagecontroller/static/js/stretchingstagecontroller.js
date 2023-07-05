$(function() {
    function stretchingstagecontrollerViewModel(parameters) {
        let self = this;

        self.name = "stretchingstagecontroller";

        self.settings = parameters[0];
        self.connectionViewModel = parameters[1];
        self.printerStateViewModel = parameters[2];
        self.filesViewModel = parameters[3];

        self.saveFileName = ko.observable();
        self.newFileName = ko.observable();

        self.selectedPorts = ko.observableArray([]);
        self.listOfPorts = ko.observableArray([]);
        self.connectedPorts = ko.observableArray([]);
        self.file_sizes = ko.observableArray([]);

        self.disabledControls = ko.pureComputed(function() {
                return self.printerStateViewModel.isBusy() ? "disabledControls" : undefined;
            }, this);

        self.dataPortConnected = ko.observable();
        self.dataPortConnected(false);

        self.pathValidated = ko.observable();
        self.pathValidated(false);

        // Wrap start print in new function for data check popup
        const startPrint = self.printerStateViewModel.print;
        const newStartPrint = function validateCOMBeforeStartingPrint() {
            if(self.dataPortConnected() == true){
                if(self.pathValidated() == true){
                    showDialog("#sidebar_startPrintDialog", function(dialog){
                        startPrint();
                        dialog .modal('hide');
                        new PNotify({
                            title: 'Serial Data Collection Started',
                            text: "Reading Serial Data...",
                            type: "info",
                            hide: true
                        });
                    });
                } else{
                    showDialog("#sidebar_filePathNotValidated", function(dialog){
                        startPrint();
                        dialog.modal('hide');
                    });
                }

            } else {
                showDialog("#sidebar_noComWarningDialog", function(dialog){
                    startPrint();
                    dialog.modal('hide');
                });
            }

        };
        self.printerStateViewModel.print = newStartPrint;

        // Wrap the "Load & Print" button into the same data check popup
        // We only intercept functionality if the user intends to print immediately after loading file.
        // i.e. printAfterLoad == true
        const oldLoad = self.filesViewModel.loadFile;
        const newLoad = function (data, printAfterLoad) {
            if (printAfterLoad) {
                if (self.dataPortConnected() == true) {
                    if (self.pathValidated() == true) {
                        showDialog("#sidebar_startPrintDialog", function (dialog) {
                            oldLoad(data, printAfterLoad);
                            dialog.modal('hide');
                            new PNotify({
                                title: 'Serial Data Collection Started',
                                text: "Reading Serial Data...",
                                type: "info",
                                hide: true
                            });
                        });
                    } else {
                        showDialog("#sidebar_filePathNotValidated", function (dialog) {
                            oldLoad(data, printAfterLoad);
                            dialog.modal('hide');
                        });
                    }
                }
                else {
                    showDialog("#sidebar_noComWarningDialog", function (dialog) {
                        oldLoad(data, printAfterLoad);
                        dialog.modal('hide');
                    });
                }
            }
            else {
                oldLoad(data, printAfterLoad);
            }
        };
        self.filesViewModel.loadFile = newLoad;


        // Dialog modal code
        function showDialog(dialogId, confirmFunction){
            // show dialog
            // sidebar_deleteFilesDialog
            let myDialog = $(dialogId);
            let confirmButton = $("button.btn-confirm", myDialog);
            let cancelButton = $("button.btn-cancel", myDialog);

            confirmButton.unbind("click");
            confirmButton.bind("click", function() {
                confirmFunction(myDialog);
            });
            myDialog.modal({
                //minHeight: function() { return Math.max($.fn.modal.defaults.maxHeight() - 80, 250); }
            }).css({
                width: 'auto',
                'margin-left': function() { return -($(this).width() /2); }
            });
        }

        self.updateFileName = function() {
            self.saveFileName(self.newFileName());
        }

        self.onBeforeBinding = function() {
            // Retrieve save file path from settings
            console.log("Data Request Output");
            console.log(self.connectionViewModel.portOptions())

            self.newFileName("text.txt");
            self.updateFileName();
            self.fetchPorts("available");

            self.dataPortConnected(false);
        }

        self.onDataUpdaterPluginMessage = function(plugin, data){
            if (plugin !== "stretchingstagecontroller") {
                return;
            }
            // Create an object that will be passed to instantiate a notification popup
            // See PNotify documentation for more information about notification parameters
            let notification = {};

            notification.buttons =
                {
                    closer_hover: false,
                    show_on_nonblock: false
                };

            switch(data.message) {

                case "ComNotConnected":
                    notification.title = 'COM Not Connected';
                    notification.text =  "Connection to the following COM port could not be established: " + data.port;
                    notification.type = "error";
                    notification.hide = true;
                    self.dataPortConnected(false);
                    self.fetchPorts("currently_connected");
                    break;

                case "ComConnected":
                    notification.title =  'COM Port Connected';
                    notification.text =  "Ready for Serial Data Readout on Port " + data.port;
                    notification.type = "success";
                    notification.hide = true;
                    self.dataPortConnected(true);
                    self.fetchPorts("currently_connected");
                    break;

                case "ports_fetched":
                    if(data.type == "available"){
                        // const index = data.ports.indexOf('/dev/ttyACM0');
                        // if (index > -1) { // only splice array when item is found
                        //   data.ports.splice(index, 1); // 2nd parameter means remove one item only
                        // }
                        self.listOfPorts(data.ports);
                    }
                    else {
                        self.connectedPorts(data.ports);
                    }
                    break;

                case "file_sizes_fetched":
                    self.file_sizes(data.file_data)
                    break;

                case "valid_filename":
                    notification.title =  'Filename Accepted';
                    notification.text =  "File will be saved at /home/pi/stretchingStage/";
                    notification.type = "info";
                    notification.hide = true;
                    self.pathValidated(true);
                    break;

                case "invalid_filename":
                    notification.title =  'Invalid Filename';
                    notification.text =  "File already exists. Please select new filename or delete conflicting file.";
                    notification.type = "error";
                    notification.hide = true;
                    break;

                case "path_does_not_exist":
                    notification.title =  'Path Does Not Exist';
                    notification.text =  "You are trying to save files to a nonexistent path. Please edit the save path in Octoprint settings to a valid path";
                    notification.type = "error";
                    notification.hide = true;
                    break;

                case "path_missing_slash":
                    notification.title =  'Save Path must end in /';
                    notification.text =  "You are trying to save files to an invalid filepath. Path must end in /. Please edit the save path in Octoprint settings";
                    notification.type = "error";
                    notification.hide = true;
                    break;

                case "com_disconnected":
                    notification.title =  'COM Port Disconnected';
                    notification.text =  "COM port " + data.port + " has been disconnected.";
                    notification.type = "error";
                    notification.hide = true;
                    self.dataPortConnected(false);
                    self.fetchPorts("currently_connected");
                    break;

                case "data_collected":
                    self.pathValidated(false);
                    break;
            }
            if(notification.title){
                new PNotify(notification);
            }

        }

        self.fetchPorts = function(type="") {
            let payload = {"type":type}
            OctoPrint.simpleApiCommand("stretchingstagecontroller", "fetchPorts", payload)
                .done(function(response){
                })
        }

        self.validateSettings = function() {
            self.updateFileName();
            let  payload = {"save_path": "/home/pi/stretchingStage/",
                "file_name": self.saveFileName()};
            OctoPrint.simpleApiCommand("stretchingstagecontroller", "validateSettings", payload)
                .done(function(response) {
                })
        }

        self.connectCOM = function() {
            let payload = {"serial_read_ports":self.selectedPorts()};
            OctoPrint.simpleApiCommand("stretchingstagecontroller", "connectCOM", payload)
                .done(function(response){
                })
        }

        self.disconnectCOM = function() {
            let payload = {};
            OctoPrint.simpleApiCommand("stretchingstagecontroller", "disconnectCOM", payload)
                .done(function(response){
                })
        }
    }


    OCTOPRINT_VIEWMODELS.push({
        construct: stretchingstagecontrollerViewModel,

        // e.g. loginStateViewModel, settingsViewModel, ...
        dependencies: ["settingsViewModel", "connectionViewModel", "printerStateViewModel", "filesViewModel" ],

        // e.g. #settings_plugin_DetailedProgress, #tab_plugin_DetailedProgress, ...
        elements: ["#tab_plugin_stretchingstagecontroller"]
    });
});

