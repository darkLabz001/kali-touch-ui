# Python payloads

Copy `hello.py` into `/home/kali/payloads/` on the device, then open
**My Scripts**. You can also use **Add .py file** in the UI,
including from another computer browsing to `http://<device-ip>:8080`.

Scripts run with Python 3 as the backend's user (`kali`), with the payloads folder
as their working directory. Python dependencies must already be installed for
that interpreter. The UI supports optional quoted command-line arguments, live
stdout/stderr, text input, exit codes, and stopping a script and its children.
One payload can run at a time. Navigating away does not stop it; reopen the same
script to view its output or stop it. The console retains the latest 32K characters.

The live folder is separate from this source directory and is preserved by app
updates. Change it with `TOUCHUI_PAYLOADS_DIR` in the backend environment if needed.
Discovery lists regular `.py` files directly in the folder. Uploads accept UTF-8
text up to 1 MiB and never replace an existing filename. Helper files or packages
can be copied into the live folder over SSH. Scripts are ordinary executable
Python code with the device user's permissions; only install scripts you trust.

## Domain OSINT

`domain_osint.py` looks up a domain's public DNS records (A, AAAA, MX, NS, TXT,
CAA), RDAP registration details, and names published in certificate-transparency
logs. It uses Python's standard library; no API key or package installation is
needed.

On the device, select **domain_osint.py**, enter `example.org` in **Arguments**,
and tap **RUN**. Or leave Arguments empty, tap RUN, then enter the domain in the
input field and tap **Send** when prompted. An HTTP/HTTPS URL is also accepted;
only its hostname is looked up.

```bash
python3 domain_osint.py example.org
python3 domain_osint.py example.org --no-ct
python3 domain_osint.py example.org --limit 10 --timeout 15
```

Text and JSON reports are saved beside the script in `reports/` (on the Pi:
`/home/kali/payloads/reports/`). JSON includes source URLs, collection time, full
returned DNS answers and matching certificate names, and individual service
errors. An unavailable service produces a partial report; if every lookup fails,
the script exits with code 1. `--output-dir` changes the report folder.

DNS comes from [Google Public DNS](https://developers.google.com/speed/public-dns/docs/doh/json),
registration from [RDAP.org and registry RDAP services](https://about.rdap.org/),
and certificate names from [crt.sh](https://crt.sh/). These services receive the
queried domain. Certificate names can be historical or wildcard entries and do
not establish that a host is currently live. RDAP expects the registered domain;
subdomains may have no registration record. Public service availability and rate
limits affect results.

## Web Surface Mapper

`web_surface_mapper.py` maps a website using Python's standard library. It crawls
HTML links, reads `robots.txt` and sitemaps, extracts literal routes from linked
JavaScript, inventories forms and password fields, and checks a small built-in
list of admin, API, documentation, backup, and configuration paths.

In **My Scripts**, use **Add .py file** to upload `web_surface_mapper.py`, select
it, and enter a full URL such as `http://192.168.1.50:8000` in **Arguments**. Tap
**RUN**. With no arguments, it prompts for the URL through **Send**.

```bash
python3 web_surface_mapper.py http://192.168.1.50:8000
python3 web_surface_mapper.py https://lab.example --max-requests 120 --depth 3
python3 web_surface_mapper.py https://lab.example --insecure --delay 0.5
python3 web_surface_mapper.py http://192.168.1.50 --wordlist paths.txt
```

Defaults: 60 total requests (including two missing-path baseline checks), crawl
depth 2, 8-second socket timeout, and at least 0.2 seconds between request starts.
`--max-requests` accepts 5–500, `--depth` accepts 0–5, `--timeout` accepts 1–30,
and `--delay` accepts 0–10 seconds. Requests are sequential. A 429 response stops
the scan. A wordlist replaces the built-in paths; use one path per line, with
optional `#` comment lines, up to 1000 paths. Path checks start at the origin root,
even if the starting URL includes a subdirectory.

Only the exact starting scheme, hostname and port are requested. External links
and redirects are recorded but not followed, including HTTP-to-HTTPS redirects;
start with the final URL when appropriate. TLS certificates are verified unless
`--insecure` is explicitly supplied. Environment HTTP proxy settings are ignored.
Use this on websites within your testing scope. Forms are never submitted, but
GET requests can still trigger application actions such as logout links.

Live output shows status codes and assessments. JSON and text reports are saved
beside the script in `reports/`; `--output-dir` changes this. Reports include URLs,
titles, redirect locations, form field names/types, errors, scan settings, and
queued URLs left unchecked. They do not save response bodies or form values.
URLs themselves can contain sensitive query parameters.

Successful responses are leads to review, not confirmed vulnerabilities. Generic
responses matching a missing-path baseline are labeled **possible wildcard /
soft 404**. Dynamic error pages can evade that heuristic; 401/403 responses do not
prove a path exists. JavaScript is parsed as text, not executed. Reads are capped
at 256 KiB per response, discovery at 2000 URLs, and the request/depth limits can
leave additional paths unexamined. **STOP** ends the process immediately; reports
are written when the scan finishes normally or reaches its request/rate limit.
