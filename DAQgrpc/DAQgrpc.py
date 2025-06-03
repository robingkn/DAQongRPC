import sys
import grpc
import numpy as np
import matplotlib.pyplot as plt
import time

import nidaqmx_pb2 as nidaqmx_types
import nidaqmx_pb2_grpc as grpc_nidaqmx

# Default values
SERVER_ADDRESS = "localhost"
SERVER_PORT = "31763"
PHYSICAL_CHANNEL = "Dev1/ai0"

# Override defaults from command-line arguments
if len(sys.argv) >= 2:
    SERVER_ADDRESS = sys.argv[1]
if len(sys.argv) >= 3:
    SERVER_PORT = sys.argv[2]
if len(sys.argv) >= 4:
    PHYSICAL_CHANNEL = sys.argv[3]

# Create a gRPC channel and client
channel = grpc.insecure_channel(f"{SERVER_ADDRESS}:{SERVER_PORT}")
client = grpc_nidaqmx.NiDAQmxStub(channel)
task = None

def check_for_warning(response):
    if response.status > 0:
        warning_message = client.GetErrorString(
            nidaqmx_types.GetErrorStringRequest(error_code=response.status)
        )
        sys.stderr.write(f"{warning_message.error_string}\nWarning status: {response.status}\n")

try:
    create_task_response = client.CreateTask(
        nidaqmx_types.CreateTaskRequest(session_name="my task")
    )
    task = create_task_response.task

    client.CreateAIVoltageChan(
        nidaqmx_types.CreateAIVoltageChanRequest(
            task=task,
            physical_channel=PHYSICAL_CHANNEL,
            terminal_config=nidaqmx_types.INPUT_TERM_CFG_WITH_DEFAULT_CFG_DEFAULT,
            min_val=-10.0,
            max_val=10.0,
            units=nidaqmx_types.VOLTAGE_UNITS2_VOLTS,
        )
    )

    client.CfgSampClkTiming(
        nidaqmx_types.CfgSampClkTimingRequest(
            task=task,
            rate=10000.0,
            active_edge=nidaqmx_types.EDGE1_RISING,
            sample_mode=nidaqmx_types.ACQUISITION_TYPE_CONT_SAMPS,
            samps_per_chan=1000,
        )
    )

    get_num_chans_response = client.GetTaskAttributeUInt32(
        nidaqmx_types.GetTaskAttributeUInt32Request(
            task=task,
            attribute=nidaqmx_types.TASK_ATTRIBUTE_NUM_CHANS
        )
    )
    number_of_channels = get_num_chans_response.value

    start_task_response = client.StartTask(nidaqmx_types.StartTaskRequest(task=task))
    check_for_warning(start_task_response)

    # --- Real-time Plotting Setup ---
    plt.ion()
    fig, ax = plt.subplots()
    max_points = 5000  # Adjust for longer history
    time_data = np.zeros(max_points)
    voltage_data = [np.zeros(max_points) for _ in range(number_of_channels)]
    lines = []
    for ch in range(number_of_channels):
        line, = ax.plot(time_data, voltage_data[ch], label=f"Channel {ch}")
        lines.append(line)
    ax.set_title("Live Plot - Analog Input")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Voltage (V)")
    ax.set_ylim(-10, 10)  # Freeze y-axis
    ax.legend()
    plt.show()

    print("Press Ctrl+C to stop...")
    start_time = time.time()
    current_index = 0

    while True:
        read_response = client.ReadAnalogF64(
            nidaqmx_types.ReadAnalogF64Request(
                task=task,
                num_samps_per_chan=1000,
                array_size_in_samps=number_of_channels * 1000,
                fill_mode=nidaqmx_types.GROUP_BY_GROUP_BY_CHANNEL,
                timeout=10.0,
            )
        )
        elapsed_time = time.time() - start_time
        timestamps = np.linspace(elapsed_time, elapsed_time + 0.1, 1000)  # 0.1s for 1000 samples at 10kHz
        data = np.array(read_response.read_array)
        data = data.reshape((number_of_channels, read_response.samps_per_chan_read))

        # Append and clip data
        for ch in range(number_of_channels):
            voltage_data[ch] = np.roll(voltage_data[ch], -1000)
            voltage_data[ch][-1000:] = data[ch]
        time_data = np.roll(time_data, -1000)
        time_data[-1000:] = timestamps

        for ch in range(number_of_channels):
            lines[ch].set_xdata(time_data)
            lines[ch].set_ydata(voltage_data[ch])

        ax.set_xlim(time_data[0], time_data[-1])
        fig.canvas.draw()
        fig.canvas.flush_events()
        plt.pause(0.001)

except KeyboardInterrupt:
    print("\nStopped by user.")

except grpc.RpcError as rpc_error:
    error_message = str(rpc_error.details() or "")
    for entry in rpc_error.trailing_metadata() or []:
        if entry.key == "ni-error":
            value = entry.value if isinstance(entry.value, str) else entry.value.decode("utf-8")
            error_message += f"\nError status: {value}"
    if rpc_error.code() == grpc.StatusCode.UNAVAILABLE:
        error_message = f"Failed to connect to server on {SERVER_ADDRESS}:{SERVER_PORT}"
    elif rpc_error.code() == grpc.StatusCode.UNIMPLEMENTED:
        error_message = (
            "The operation is not implemented or is not supported/enabled in this service"
        )
    print(f"{error_message}")

finally:
    if task:
        client.StopTask(nidaqmx_types.StopTaskRequest(task=task))
        client.ClearTask(nidaqmx_types.ClearTaskRequest(task=task))
    plt.ioff()
    plt.close()
