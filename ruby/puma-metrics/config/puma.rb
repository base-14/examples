require "yabeda"
require "yabeda/puma/plugin"

workers 2
threads 2, 4

bind "tcp://0.0.0.0:3000"

# Required — yabeda-puma-plugin uses Puma's control app hooks to read internal stats.
# Without this line the plugin has no stats source and Puma fails to boot.
activate_control_app
plugin :yabeda

# Non-Rails apps must call Yabeda.configure! before workers fork.
# Rails apps get this automatically via the yabeda railtie.
before_fork do
  Yabeda.configure!
end
