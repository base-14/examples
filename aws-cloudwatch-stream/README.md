# AWS CloudWatch Metrics to Otel Collector

This folder contains the source code used for in the
process of getting aws cloudwatch metrics to otel
collector via kinesis streams.

Follow the docs at https://docs.base14.io/instrument/infra/aws/collecting-aws-cloudwatch-metrics-using-kinesis-streams

In this method
We'll configure the cloudwatch to use kinesis streams
to stream the metrics to a S3 bucket and we'll have
a lambda function to read from the s3 bucket and 
push it to a otel collector.


