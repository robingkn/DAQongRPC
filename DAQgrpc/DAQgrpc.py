import sys
import time
import grpc
import numpy as np
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt5.QtCore import QTimer
import pyqtgraph as pg

import nidaqmx_pb2 as nidaqmx_types
import nidaqmx_pb2_grpc as grpc_nidaqmx


class LivePlotWidget(pg.PlotWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Live gRPC NI-DAQ Data")
        self.setLabel('left', 'Voltage (V)')
        self.setLabel('bottom', 'Time (ms)')
        self.showGrid(x=True, y=True)
        self.curves = []
        self.x_data = []
        self.y_data = []

    def setup_channels(self, num_channels):
        self.curves = []
        self.y_data = [list() for _ in range(num_channels)]
        colors = ['g','r', 'b', 'y', 'c']
        for i in range(num_channels):
            curve = self.plot(pen=colors[i % len(colors)])
            self.curves.append(curve)

    def update_plot(self, timestamps, voltage_matrix):
        self.x_data.extend(timestamps)

        for ch in range(len(voltage_matrix)):
            self.y_data[ch].extend(voltage_matrix[ch])

        # Keep 10 seconds max
        ten_seconds_ago = timestamps[-1] - 10_000
        while self.x_data and self.x_data[0] < ten_seconds_ago:
            self.x_data.pop(0)
            for ch in self.y_data:
                ch.pop(0)

        for i, curve in enumerate(self.curves):
            curve.setData(self.x_data, self.y_data[i])
        self.setXRange(max(0, timestamps[-1] - 10_000), timestamps[-1])


class LivePlotWindow(QMainWindow):
    def __init__(self, channel="Dev1/ai0", sample_rate=1000, server="localhost", port="31763"):
        super().__init__()
        self.setWindowTitle("gRPC NI-DAQ Live Plot with PyQtGraph")
        self.setGeometry(100, 100, 800, 400)

        self.plot_widget = LivePlotWidget()
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.addWidget(self.plot_widget)
        self.setCentralWidget(central_widget)

        self.sample_rate = sample_rate
        self.start_time = time.time()

        self.channel_name = channel
        self.task = None

        # gRPC setup
        self.channel = grpc.insecure_channel(f"{server}:{port}")
        self.client = grpc_nidaqmx.NiDAQmxStub(self.channel)

        self.setup_task()

        self.timer = QTimer()
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.update_data)
        self.timer.start()

    def setup_task(self):
        create_resp = self.client.CreateTask(nidaqmx_types.CreateTaskRequest(session_name="pyqt_task"))
        self.task = create_resp.task

        self.client.CreateAIVoltageChan(nidaqmx_types.CreateAIVoltageChanRequest(
            task=self.task,
            physical_channel=self.channel_name,
            terminal_config=nidaqmx_types.INPUT_TERM_CFG_WITH_DEFAULT_CFG_DEFAULT,
            min_val=-10.0,
            max_val=10.0,
            units=nidaqmx_types.VOLTAGE_UNITS2_VOLTS
        ))

        self.client.CfgSampClkTiming(nidaqmx_types.CfgSampClkTimingRequest(
            task=self.task,
            rate=self.sample_rate,
            active_edge=nidaqmx_types.EDGE1_RISING,
            sample_mode=nidaqmx_types.ACQUISITION_TYPE_CONT_SAMPS,
            samps_per_chan=1000
        ))

        num_chan = self.client.GetTaskAttributeUInt32(nidaqmx_types.GetTaskAttributeUInt32Request(
            task=self.task,
            attribute=nidaqmx_types.TASK_ATTRIBUTE_NUM_CHANS
        )).value

        self.plot_widget.setup_channels(num_chan)
        self.client.StartTask(nidaqmx_types.StartTaskRequest(task=self.task))

    def update_data(self):
        try:
            read_resp = self.client.ReadAnalogF64(nidaqmx_types.ReadAnalogF64Request(
                task=self.task,
                num_samps_per_chan=500,
                array_size_in_samps=500,
                fill_mode=nidaqmx_types.GROUP_BY_GROUP_BY_CHANNEL,
                timeout=1.0
            ))

            if read_resp.samps_per_chan_read == 0:
                return

            now = time.time()
            latest_time = (now - self.start_time) * 1000
            sample_period_ms = 1000 / self.sample_rate
            timestamps = [latest_time - sample_period_ms * (read_resp.samps_per_chan_read - 1 - i)
                          for i in range(read_resp.samps_per_chan_read)]

            data = np.array(read_resp.read_array)
            data = data.reshape((len(self.plot_widget.curves), read_resp.samps_per_chan_read))

            self.plot_widget.update_plot(timestamps, data.tolist())

        except grpc.RpcError as e:
            print("gRPC error:", e)

    def closeEvent(self, event):
        try:
            if self.task:
                self.client.StopTask(nidaqmx_types.StopTaskRequest(task=self.task))
                self.client.ClearTask(nidaqmx_types.ClearTaskRequest(task=self.task))
        except Exception as e:
            print("Error closing task:", e)
        finally:
            super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LivePlotWindow(channel="Dev1/ai0", sample_rate=1000)
    window.show()
    sys.exit(app.exec_())
