# TLS Certificate Expiry

Symptoms: clients report "certificate has expired"; x509 handshake failures; a jump
in auth or connection errors right after a known expiry time.
Likely causes: a cert that was not renewed, a failed cert-manager renewal, or a
clock skew making a valid cert look expired.
Diagnostics: check the cert's notAfter with `openssl s_client -connect host:443`;
grep logs for "x509" / "certificate has expired"; inspect cert-manager events.
Remediation: renew and roll out the certificate, restart the pods that cached the
old one, and verify the new expiry. Fix the renewal automation so it recurs.
Escalation: page security/PKI owners if the renewal pipeline itself is broken.
