Generating gRPC Python Bindings for NI-DAQmx
Install prerequisites:

pip install grpcio grpcio-tools

Clone the NI gRPC Device repository (shallow clone):

git clone --depth 1 https://github.com/ni/grpc-device.git

Locate the required .proto files:

generated/nidaqmx/nidaqmx.proto

imports/protobuf/session.proto

imports/protobuf/data_moniker.proto

Generate the Python gRPC bindings using grpc_tools.protoc:

python -m grpc_tools.protoc -Iimports/protobuf -Igenerated --python_out=. --grpc_python_out=. generated/nidaqmx/nidaqmx.proto

Result:

The following files will be generated:

nidaqmx/nidaqmx_pb2.py

nidaqmx/nidaqmx_pb2_grpc.py

How to use in your Python code:

from nidaqmx import nidaqmx_pb2, nidaqmx_pb2_grpc

(Ensure the nidaqmx folder is in your PYTHONPATH or your working directory.)

Run the gRPC server:	