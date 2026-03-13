# Run with: mix run run.exs

HelloWorld.say_hello()
HelloWorld.check_disk_space()
HelloWorld.parse_config()

# Flush all buffered telemetry to the collector before exiting.
# Without this, the last batch of spans may be lost.
# force_flush is async in the Erlang OTel SDK — the brief sleep ensures
# the batch processor completes the HTTP export before the VM exits.
:otel_tracer_provider.force_flush()
Process.sleep(500)

IO.puts("Done. Check Scout for your traces.")
