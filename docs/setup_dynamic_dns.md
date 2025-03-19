# Setup Dynamic DNS

1. In Unifi, add Dynamic DNS entry (leave server empty in case of Loopia)
1. Setup port forwarding in Unifi (ports `80`, `443` for http, https)
1. Too see if it works: On server `sudo nc -l 80`. On another computer, `curl http://endpoint.example.com`.
