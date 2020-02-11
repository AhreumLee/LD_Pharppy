"""
GUI for controlling the Picoharp300, choosing settings, visualizing and
exporting histograms.

This script is fairly alpha status at the moment. Comments/questions/requests
are welcome - email david@lownd.es or through github.com/dldlowndes/LD_Pharppy)

Requires: Python 3.7+, Numpy, PyQt5, PyQtGraph.
"""

import sys

import numpy as np
from PyQt5 import QtWidgets, QtCore
import pyqtgraph

import acq_Thread
from settings_gui import Ui_Settings

import LD_Pharp
#import LD_Pharp_Dummy as LD_Pharp


class my_Window(QtWidgets.QMainWindow):
    def __init__(self):
        super(my_Window, self).__init__()
        self.ui = Ui_Settings()
        self.ui.setupUi(self)

        # Connect UI elements to functions
        self.ui.button_ApplySettings.clicked.connect(self.apply_Settings)
        self.ui.button_Defaults.clicked.connect(self.apply_Default_Settings)
        self.ui.button_StartStop.clicked.connect(self.start_Stop)
        self.ui.button_SaveHisto.clicked.connect(self.on_Save_Histo)
        self.ui.button_AutoRange.clicked.connect(self.on_Auto_Range)

        # Modify the plot window
        self.ui.graph_Widget.plotItem.setLabel("left", "Counts")
        self.ui.graph_Widget.plotItem.setLabel("bottom", "Time", "s")
        self.ui.graph_Widget.plotItem.showGrid(x=True, y=True)
        self.ui.graph_Widget.plotItem.showButtons()

        # Set up crosshairs for markers, one that follows the mouse and two
        # that persist after click (for one click before they move again)
        self.v_Line = pyqtgraph.InfiniteLine(angle=90, movable=False)
        self.h_Line = pyqtgraph.InfiniteLine(angle=0, movable=False)
        self.v_Line_1 = pyqtgraph.InfiniteLine(angle=90, movable=False, pen='r')
        self.h_Line_1 = pyqtgraph.InfiniteLine(angle=0, movable=False, pen='r')
        self.v_Line_2 = pyqtgraph.InfiniteLine(angle=90, movable=False, pen='g')
        self.h_Line_2 = pyqtgraph.InfiniteLine(angle=0, movable=False, pen='g')
        self.ui.graph_Widget.addItem(self.v_Line, ignoreBounds=True)
        self.ui.graph_Widget.addItem(self.h_Line, ignoreBounds=True)

        # Keep track of which crosshair should move on the next click.
        self.first_Click = True
        # Last click has to be somewhere so just stick it at the origin.
        # Holds the co-ordinates of the most previous click.
        self.last_Click = QtCore.QPoint(0, 0)

        # Mouse events
        self.proxy = pyqtgraph.SignalProxy(
                                self.ui.graph_Widget.sceneObj.sigMouseMoved,
                                rateLimit=60,
                                slot=self.on_Mouse_Move)
        self.ui.graph_Widget.sceneObj.sigMouseClicked.connect(
                                                        self.on_Graph_Click)

        # Connect to the actual device.
        self.my_Pharp = LD_Pharp.LD_Pharp(0)

        # The resolutions are all 2**n multiples of the base resolution so
        # get the base resolution from the device and work out all of the
        # resolutions to display in the dropdown box.
        self.base_Resolution = self.my_Pharp.base_Resolution
        allowed_Resolutions = [self.base_Resolution * (2**n) for n in range(8)]
        for i, res in enumerate(allowed_Resolutions):
            self.ui.resolution.addItem(f"{res}")
        self.ui.resolution.setCurrentText(f"self.base_Resolution")

        # Set up some default settings.
        self.ui.filename.setText(f"save_filename.csv")
        self.histogram_Running = False
        self.ui.status.setText("Counting")
        self.current_Options = {}
        self.apply_Default_Settings()
        self.count_Precision = 3

        # Make the worker thread.
        self.acq_Thread = acq_Thread.Acq_Thread(self.my_Pharp)
        self.acq_Thread.count_Signal.connect(self.on_Count_Signal)
        self.acq_Thread.plot_Signal.connect(self.on_Histo_Signal)
        self.acq_Thread.start()

    def apply_Settings(self):
        """
        Get the settings from the UI and tell the picoharp to update them.
        """

        # Hardware complains if you push settings while histogram is running,
        # it might lead to it ending up in an undefined state so just forbid
        # sending settings while the histogram is running
        if self.histogram_Running:
            print("Settings not pushed, histogram is running")
        else:
            # Translate desired resolution to a "binning" number. Binning
            # combines histogram bins to reduce the histogram resolution.
            resolution_Req = self.ui.resolution.currentText()
            binning = np.log2(float(resolution_Req) / self.base_Resolution)

            options = {
                    "binning": int(binning),
                    "sync_Offset": int(self.ui.sync_Offset.value()),
                    "sync_Divider": int(self.ui.sync_Divider.currentText()),
                    "CFD0_ZeroCross": int(self.ui.CFD0_Zerocross.value()),
                    "CFD0_Level": int(self.ui.CFD0_Level.value()),
                    "CFD1_ZeroCross": int(self.ui.CFD1_Zerocross.value()),
                    "CFD1_Level": int(self.ui.CFD1_Level.value()),
                    "acq_Time": int(self.ui.acq_Time.value())
                    }

            print(options)
            self.my_Pharp.Update_Settings(**options)

            # Remember the settings that were last pushed.
            self.current_Options = options

            # If binning (resolution) changes, the histogram x axis labels
            # change. Update this. The max number of bins is 65536, this will
            # be trimmed in the plotting function.
            x_Min = 0
            x_Max = 65536 * self.my_Pharp.resolution
            x_Step = self.my_Pharp.resolution
            self.x_Data = np.arange(x_Min, x_Max, x_Step)
            self.x_Data /= 1e12  # convert to seconds

    def apply_Default_Settings(self):
        """
        Some sensible defaults of the options. Sets the UI elements to the
        defaults and then calls the function that reads them and pushes.
        """
        default_Options = {
                "binning": 0,
                "sync_Offset": 0,
                "sync_Divider": 1,
                "CFD0_ZeroCross": 10,
                "CFD0_Level": 50,
                "CFD1_ZeroCross": 10,
                "CFD1_Level": 50,
                "acq_Time": 500
                }

        binning = default_Options["binning"]
        resolution = self.base_Resolution * (2 ** binning)

        self.ui.resolution.setCurrentText(f"{resolution}")
        self.ui.sync_Offset.setValue(default_Options["sync_Offset"])
        self.ui.sync_Divider.setCurrentText(
                str(default_Options["sync_Divider"]))
        self.ui.CFD0_Level.setValue(default_Options["CFD0_Level"])
        self.ui.CFD0_Zerocross.setValue(default_Options["CFD0_ZeroCross"])
        self.ui.CFD1_Level.setValue(default_Options["CFD1_Level"])
        self.ui.CFD1_Zerocross.setValue(default_Options["CFD1_ZeroCross"])
        self.ui.acq_Time.setValue(default_Options["acq_Time"])

        self.apply_Settings()

    def start_Stop(self):
        # Switch modes from counting to histogramming.
        if self.acq_Thread.histogram_Active:
            print("Stop histo")
            self.ui.status.setText("Counting")
            self.acq_Thread.histogram_Active = False
        else:
            print("Start histo")
            self.ui.status.setText("Histogramming")
            self.acq_Thread.histogram_Active = True

    def on_Count_Signal(self, ch0, ch1):
        self.ui.counts_Ch0.setText(f"{ch0:.{self.count_Precision}E}")
        self.ui.counts_Ch1.setText(f"{ch1:.{self.count_Precision}E}")

    def on_Histo_Signal(self, histogram_Data):
        # There are 65536 bins, but if (1/sync) is less than (65536*resolution)
        # then there will just be empty bins at the end of the histogram array.
        # Look from the END of the array and find the index of the first non
        # empty bin you find.
        last_Full_Bin = histogram_Data.nonzero()[0][-1]

        # Trim the histogram and labels so the empty bins (that will never
        # fill) are not plotted. Then plot them.
        self.ui.graph_Widget.plot(self.x_Data[:last_Full_Bin],
                                  histogram_Data[:last_Full_Bin],
                                  clear=True)
        self.ui.graph_Widget.addItem(self.v_Line, ignoreBounds=True)
        self.ui.graph_Widget.addItem(self.h_Line, ignoreBounds=True)
        # Remember the last histogram, so it can be saved.
        self.last_Histogram = histogram_Data
        self.last_X_Data = self.x_Data

    def on_Save_Histo(self):
        """
        This actually still works when histogramming is running but obviously
        there won't be certainty as to exactly what the histogram looks like.
        """
        filename = self.ui.filename.text()

        # Zip the bins and counts together for export.
        hist_Out = np.column_stack((self.last_X_Data, self.last_Histogram))

        np.savetxt(filename,
                   hist_Out,
                   delimiter=", "
                   )

    def on_Auto_Range(self):
        """
        Tell the plot widget to fit the full histogram on the plot.
        """
        self.ui.graph_Widget.plotItem.autoBtnClicked()

    def on_Mouse_Move(self, evt):
        """
        Move the crosshair that follows the mouse to the mouse position.
        """

        vb = self.ui.graph_Widget.plotItem.vb
        coords = vb.mapSceneToView(evt[0])

        self.v_Line.setPos(coords.x())
        self.h_Line.setPos(coords.y())

        self.ui.current_X.setText(f"{coords.x():3E}")
        self.ui.current_Y.setText(f"{coords.y():3E}")

    def on_Graph_Click(self, evt):
        """
        Put a crosshair on the plot in the click location. There are two
        crosshairs so x and y differences can be calculated between click
        positions. The crosshair that moves alternates and the difference
        is calculated every click.
        """

        vb = self.ui.graph_Widget.plotItem.vb
        coords = vb.mapSceneToView(evt.scenePos())

        if self.first_Click:
            self.first_Click = False
            print(f"first {coords}")
            self.v_Line_1.setPos(coords.x())
            self.h_Line_1.setPos(coords.y())
            self.ui.graph_Widget.addItem(self.v_Line_1, ignoreBounds=True)
            self.ui.graph_Widget.addItem(self.h_Line_1, ignoreBounds=True)
            self.ui.click_1_X.setText(f"{coords.x():3E}")
            self.ui.click_1_Y.setText(f"{coords.y():3E}")

        else:
            self.first_Click = True
            print(f"second {coords}")
            self.v_Line_2.setPos(coords.x())
            self.h_Line_2.setPos(coords.y())
            self.ui.graph_Widget.addItem(self.v_Line_2, ignoreBounds=True)
            self.ui.graph_Widget.addItem(self.h_Line_2, ignoreBounds=True)
            self.ui.click_2_X.setText(f"{coords.x():3E}")
            self.ui.click_2_Y.setText(f"{coords.y():3E}")

        self.ui.delta_X.setText(f"{coords.x() - self.last_Click.x():3E}")
        self.ui.delta_Y.setText(f"{coords.y() - self.last_Click.y():3E}")
        self.last_Click = coords


app = QtWidgets.QApplication([])

application = my_Window()

application.show()

sys.exit(app.exec())
