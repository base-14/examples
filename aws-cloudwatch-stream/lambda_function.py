import requests
import boto3
import os
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest

# CONFIGURE THESE:
OTEL_COLLECTOR_URL = os.environ.get('OTEL_COLLECTOR_URL')

# Initialize the S3 client
s3_client = boto3.client('s3')

def send_metrics_to_otel(request_obj):
    headers = {
        "Content-Type": "application/x-protobuf",
    }
    payload = request_obj.SerializeToString()
    response = requests.post(OTEL_COLLECTOR_URL, headers=headers, data=payload)
    if response.status_code == 200:
        print("Metrics successfully forwarded.")
    else:
        print(
            f"Failed to send metrics. Status: {response.status_code}, "
            f"Response: {response.text}"
        )

def load_and_parse_file(bucket, key):
    # Fetch the file from S3
    response = s3_client.get_object(  
        Bucket=bucket, Key=key  
    )
    data = response['Body'].read()  # Read the entire file as bytes
    return data

def parse_metrics(data):
    offset = 0
    total_len = len(data)
    messages = []

    while offset < total_len:
        # Read the varint (length prefix)
        msg_len, new_pos = _DecodeVarint32(data, offset)
        if msg_len <= 0:
            print("Invalid message length.")
            break
        
        # Extract the actual protobuf message based on the length
        msg_buf = data[new_pos:new_pos + msg_len]

        try:
            # Parse the protobuf message
            request = ExportMetricsServiceRequest()
            request.ParseFromString(msg_buf)
            messages.append(request)
            print(f"Parsed ExportMetricsServiceRequest at offset {offset}.")
        except DecodeError as e:
            print(f"Decode error at offset {offset}: {e}")
            break

        # Move the offset by the length of the message
        offset = new_pos + msg_len

    return messages

def _DecodeVarint32(buf, position):
    # Decodes a varint32 (unsigned 32-bit integer) from the buffer
    # It returns the decoded varint value and the new position in the buffer
    shift = 0
    result = 0
    while True:
        byte = buf[position]
        position += 1
        result |= (byte & 0x7F) << shift
        if byte & 0x80 == 0:
            break
        shift += 7
    return result, position

def process_s3_directory(bucket, prefix=''):
    # List all files in the specified S3 directory (including subdirectories)
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter='/')

    # Process files directly in the current directory
    for obj in response.get('Contents', []):
        file_key = obj['Key']
        print(f"Processing file: {file_key}")
        try:
            data = load_and_parse_file(bucket, file_key)
            metrics = parse_metrics(data)
            for metric in metrics:
                send_metrics_to_otel(metric)
        except Exception as e:
            print(f"Error processing file {file_key}: {e}")
    
    # Recursively process subdirectories (if any)
    for prefix_dir in response.get('CommonPrefixes', []):
        subdir_prefix = prefix_dir['Prefix']
        print(f"Descending into subdirectory: {subdir_prefix}")
        process_s3_directory(bucket, subdir_prefix)

def lambda_handler(event, context):
    # Check if this is being triggered by an S3 event
    if 'Records' in event and event['Records'][0].get('eventSource') == 'aws:s3':
        print("Lambda triggered by S3 event.")
        
        # Get the bucket name and object key from the S3 event
        bucket_name = event['Records'][0]['s3']['bucket']['name']
        file_key = event['Records'][0]['s3']['object']['key']
        
        # Process the directory where the file is located
        process_s3_directory(bucket_name)
    else:
        print("Lambda triggered manually.")
        
        bucket_name = os.environ.get('S3_BUCKET_NAME', event.get('bucket_name', S3_BUCKET_NAME))
        prefix = os.environ.get('S3_PREFIX', event.get('prefix', ''))
        
        if not bucket_name:
            return {
                'statusCode': 400,
                'body': 'Missing S3_BUCKET_NAME in environment variables'
            }
        
        print(f"Processing bucket: {bucket_name} with prefix: {prefix}")
        process_s3_directory(bucket_name, prefix)

    return {
        'statusCode': 200,
        'body': 'Metrics successfully processed and forwarded to OTEL Collector'
    }
