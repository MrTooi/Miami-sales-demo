# Step R: hosting and login research for the website trial (issue #131)

- **Date:** 2026-10-27. **Author:** Claude Code, step R of the reviewed plan in issue #131 (plan v7, manual review PASS WITH WARNINGS).
- **What this is:** desk research from the providers' **official documentation and pricing pages** only, plus one memory measurement with made-up files. Nothing was signed up for, bought or set up. No real shop data was used.
- **What this isn't:** proof that the design works. Everything marked **To test** must be shown on a real test setup in P2 or P4, as the plan says. Prices are list prices seen on 2026-10-27; they must be checked again before anything is bought.
- **Labels:** **Verified** = the provider's own page says it plainly. **Unclear** = the page is silent or contradicts itself. **Not available** = not on the plan we'd use.
- Sources are links to the providers' own pages. Quotes are kept short; everything else is paraphrased.
- **How it was checked:** two research passes read the official pages and labelled each answer. Claude then re-read the most important ones itself on 2026-10-27:
  - Cloudflare: session management (logout, cancellation, renewal, timing); the June 2026 change of the default login method; Enterprise-only WAF payload logging; the default cache list;
  - Render: that background workers receive no incoming traffic, and its worker sizes;
  - Fly.io: its prices, the swap setting, and its AI sub-processor entry.
  Render's prices couldn't be read by that re-check (the page didn't show them) and are marked so. Every other row has its link, so the reviewer can check it.

## Summary (plain words)
- **The login gate: Cloudflare Access, free plan** (up to 50 users). It has the emailed code, a tunnel with no open port, and a documented "cancel this person's login everywhere" call. **We must switch on the emailed code ourselves**: since June 2026 it's no longer the default.
- **The server: Render, a "background worker" with 2 GB of memory, in a US region.** A background worker **can't receive traffic from the internet at all**, so the only way in is the tunnel. It has a dashboard stop button for emergencies, and automatic deploys can be switched off. List price about **$25 a month** (check before buying). **Cheaper option:** Fly.io at about **$13.39 a month** for 2 GB, but it's run mostly from the command line, and staying private depends on getting its settings exactly right.
- **Memory:** MargenX needs about 160 MB at rest and up to about 280 MB while reading one of the largest files it accepts (made-up files, measured). **512 MB is too small** for several shops at once; 2 GB is comfortable.
- **The retention gate** (no provider keeps file contents): **met on paper for Cloudflare** (no body logging on the free plan, no bodies in request logs, caching can be switched off). **For Render, two things aren't documented: swap and crash dumps.** We ask Render support in writing before P4. If Render can't confirm, the gate isn't met there, and we use Fly.io, where swap is switched on only by a setting (implied by its docs; to confirm).
- **Domain:** the free Cloudflare plan needs the **whole domain** managed by Cloudflare. **Recommended: a separate small domain just for MargenX**, so Abrey's website and email aren't touched. That is a question for Alex and Abrey before P4.
- **No deal-breaker found.** Section 4 lists the details that change in the later steps (none changes the design). Section 5 lists what only a live test can prove.
- **Estimated running cost for a trial month:** about $25 (Render 2 GB) + $0 (Cloudflare free) + a domain (price to check, paid yearly). Nothing is bought until Alex approves a budget.


## 1. The login gate: Cloudflare Access (Zero Trust)

### 1.1 Plan and cost
| Question | Finding | Label | Source |
|---|---|---|---|
| Free plan | Up to 50 users. Access (the login gate) is included. | Verified | [Zero Trust plans](https://www.cloudflare.com/plans/sase-zero-trust.md) |
| Tunnel and emailed codes on Free | Not named on the pricing page; their own docs list no plan limit. | Unclear (no limit documented) | [Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/), [One-time PIN](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/) |
| Above 50 users | Pay-as-you-go $7 per user per month (list price). | Verified | [Zero Trust plans](https://www.cloudflare.com/plans/sase-zero-trust.md) |
| Commercial use on Free | The subscription agreement covers Free services; no ban on commercial use was found. Free services carry no liability from Cloudflare. | Verified (no ban found) | [Terms](https://www.cloudflare.com/terms/) |
| Login log retention on Free | 24 hours. | Verified | [Logs](https://developers.cloudflare.com/cloudflare-one/insights/logs/) |
| Support on Free | Community forum only. | Verified | [Zero Trust plans](https://www.cloudflare.com/plans/sase-zero-trust.md) |

### 1.2 The emailed one-time code
- **Not the default any more.** Since 2026-06-18, new Zero Trust accounts start with "sign in with a Cloudflare account" instead of the emailed code. **We must add the emailed code ourselves and make it the MargenX app's only login method** (with "instant authentication" on). Verified: [changelog 2026-06-18](https://developers.cloudflare.com/changelog/post/2026-06-18-cloudflare-idp-default/), [self-hosted apps](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/).
- **How codes behave:** a code works once and expires after 10 minutes. The email is sent only if a rule allows that address, but the login page always says "sent", so it doesn't reveal who is invited. Verified: [One-time PIN](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/).
- **Exact emails only.** The allow rule lists exact addresses. **Never** "Everyone", the "login method = one-time code" selector, or "Bypass" on this app: Cloudflare's own page warns that the first two let anyone in. Verified: [Policies](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/).

### 1.3 Sessions and renewal
- Three lengths: the **overall (global) session** (15 minutes to 1 month, default 24 hours), the **app session**, and an optional **rule (policy) session**. The most specific one wins. Verified: [Session management](https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/).
- **Renewal:** when an app token expires, Access quietly issues a new one if the overall session is still valid and the person still passes the rule. Otherwise they log in again, which for us means a new emailed code. Verified: same page.
- **For P4:** set the overall and app sessions to match (the plan's working-day length), so a login never outlives what the guide says.

### 1.4 Logout and person-wide cancellation (the plan's logout design)
- **Per-person cancellation exists:** an API call (`POST /accounts/{account_id}/access/organizations/revoke_user`, with the email) revokes that person's Access tokens **across all apps in the account**. Verified: [revoke_user API](https://developers.cloudflare.com/api/resources/zero_trust/subresources/organizations/methods/revoke_users/), [Session management](https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/).
- **What its answer confirms:** only that the request was accepted (`"success": true`), not when every session has ended. **So in the plan, "the gate confirms" can only mean "the gate accepted the cancellation".** The door's own refusal must cover the time it takes to apply. Verified (response format); timing Unclear.
- **Timing:** after a cancellation, the person can't log back in for up to 1 minute. After a logout, tokens already issued keep working for 20–30 seconds. Verified: [Session management](https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/). **Consequence for P2:** the door's refusal after a logout must be **at least 2 minutes**, not the 60 seconds in the plan, so it outlasts both documented delays with a margin. This is a detail inside P2 (test requirement 8), not a design change.
- **A cancellation isn't a ban.** The page says a person whose identity is still active can start a new session. With emailed codes, "active" means their email is still on the allow rule. So **logging back in after a cancellation should need a new emailed code**, but the page doesn't say so outright. **To test** in P4 (test requirement 21), with two devices.
- **To remove someone for good** (trial end, early end): take the email off the allow rule **first**, then cancel. Verified (that order): same page.
- **The logout address** (`/cdn-cgi/access/logout`) ends the person's session **in all apps of that account**. That is one more reason for **a separate Cloudflare account just for MargenX** (section 1.8). Verified: same page.
- **The narrowest key:** a "Access: Organizations Revoke" permission was added on 2026-01-22. The API page still lists the broader "Organizations, Identity Providers, and Groups Write". Whether the narrow one is accepted is **Unclear; to test** first in P4. If only the broad one works, the key could change login settings, so it must be kept as carefully as a password. Sources: [changelog 2026-01-22](https://developers.cloudflare.com/changelog/post/2026-01-22-granular-api-token-permissions/), [permissions](https://developers.cloudflare.com/fundamentals/api/reference/permissions/).

### 1.5 The signed token the door checks
- The door checks the `Cf-Access-Jwt-Assertion` header (not the cookie): RS256 signature, audience (the app's AUD tag), issuer (`https://<team>.cloudflareaccess.com`) and expiry. Keys are fetched from the team's `certs` address and matched by `kid`. Verified: [Validating the token](https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/).
- **Key rotation:** every 6 weeks by default, with the old key valid for 7 more days. The door caches keys and, for an unknown `kid`, re-fetches once before refusing (test requirement 7). Verified: same page.

### 1.6 The tunnel and open live connections
- **No inbound ports:** `cloudflared` only connects out (port 7844, plus 443). The server's firewall can block all incoming traffic. Verified: [Tunnel with firewall](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/).
- **"Protect with Access" at the tunnel:** `cloudflared` can check the Access token itself before passing a request on. This is an extra layer; the door still checks every request. Verified: [Origin configuration](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/origin-configuration/). Pin the `cloudflared` version (2026.10.0 changed how addresses are matched).
- **Open live connections (WebSockets):** supported on all plans. **No Cloudflare page says an open connection is cut when a token expires or is revoked.** For SSH-type apps Cloudflare says it doesn't control an active session's length. Unclear, treated as **no**. Sources: [WebSockets](https://developers.cloudflare.com/network/websockets/), [Session management](https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/). **This confirms the plan's design:** the door itself closes open connections at the token's expiry, at the trial's end moment, and on a logout, cancellation or emergency switch.

### 1.7 Retention: the plan's retention gate
| Possible place a file could be kept | Finding | Label | Source |
|---|---|---|---|
| Request logs | The HTTP request log fields have **no body field** (only a size). | Verified | [HTTP request fields](https://developers.cloudflare.com/logs/logpush/logpush-job/datasets/zone/http_requests/) |
| Firewall (WAF) payload logging | Opt-in (needs our own public key) and **Enterprise only**. Can't be on by accident on Free. | Verified / Not available | [Payload logging](https://developers.cloudflare.com/waf/managed-rules/payload-logging/) |
| DLP payload logging and forensic copies | Opt-in; forensic copies are Enterprise only. They apply to Gateway traffic from enrolled devices, not to visitors of an Access-protected app like ours. | Verified (plans); our setup inferred | [DLP logging](https://developers.cloudflare.com/cloudflare-one/data-loss-prevention/dlp-policies/logging-options/) |
| Cache | Web pages aren't cached by default, **but CSV, XLS and XLSX are on the default cached list.** We need a **"bypass cache" rule for the whole MargenX address**, plus "don't store" on every response. | Verified | [Default cache](https://developers.cloudflare.com/cache/concepts/default-cache-behavior/), [Cache rules](https://developers.cloudflare.com/cache/how-to/cache-rules/create-dashboard/) |
| Request buffering | A setting with three modes: Standard (default; inspects the start of the body if a security feature needs it), Full (holds the whole body) and None (streams it). Whether Free can change it is Unclear. Either way the body passes through Cloudflare's memory. | Verified (modes); Free Unclear | [Configuration rules settings](https://developers.cloudflare.com/rules/configuration-rules/settings/), [changelog 2026-01-27](https://developers.cloudflare.com/changelog/post/2026-01-27-body-buffering-settings/) |
| Memory while passing through | Not documented. Nothing found suggests storage. | Unclear | — |
| Login records | Email, user ID, IP, country, app, allow/deny, time. Kept 24 hours on Free. User records (emails) **can't be deleted**, even after a seat is removed. | Verified | [Audit logs](https://developers.cloudflare.com/cloudflare-one/insights/logs/audit-logs/), [Seat management](https://developers.cloudflare.com/cloudflare-one/team-and-resources/users/seat-management/) |

**Retention-gate verdict for Cloudflare (desk research):** it **can be met** on Free. Body logging isn't offered on Free, request logs carry no bodies, and caching can be switched off for the address. P4 still records the actual settings, and the privacy notice names Cloudflare for passing copies in memory and for the emails it keeps.

### 1.8 Domain, account and where data is processed
- **The domain must be fully on Cloudflare.** The MargenX address must be in a domain whose name servers point to Cloudflare, **in the same Cloudflare account**. A partial setup that moves only one address needs the **Business** plan, and sub-domain zones need Enterprise. Verified: [Partial setup](https://developers.cloudflare.com/dns/zone-setups/partial-setup/), [Subdomain setup](https://developers.cloudflare.com/dns/zone-setups/subdomain-setup/), [Tunnel DNS](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/routing-to-tunnel/dns/).
- **What that means for Abrey's website** (for the website questions before P4): using our existing domain would mean moving **the whole domain's** name servers to Cloudflare, which touches the website and email settings. **A separate small domain just for MargenX**, in its own Cloudflare account, avoids touching Abrey's site at all. Abrey's site would just get a "Log in" link. **Recommended**, to confirm with Alex and Abrey before P4.
- **A separate Cloudflare account for MargenX** keeps logouts and cancellations (which act on the whole account) away from anything else. Recommended.
- **Where data is processed:** encrypted traffic is opened at whichever Cloudflare data center receives it. Keeping it in one region needs the Data Localization Suite, an **Enterprise** add-on. So **no "US-only" claim** can be made for the gate. Sources: [Data localization](https://developers.cloudflare.com/data-localization/), [Regional services](https://developers.cloudflare.com/data-localization/regional-services/).
- **Contract terms:** Cloudflare is a processor under its data processing agreement (DPA, v6.4), and the terms keep ownership of content with us. **Whether the DPA applies to a Free account without a separate step is Unclear**; to check before T. Sources: [DPA](https://www.cloudflare.com/cloudflare-customer-dpa/), [Terms](https://www.cloudflare.com/terms/).

### 1.9 Alternatives compared
- **oauth2-proxy** (run by us): a gate in front of the app, but it has **no emailed code** of its own. It needs a separate login provider, its own route in, and certificates we manage, and no cancellation API is documented. More moving parts. [oauth2-proxy](https://oauth2-proxy.github.io/oauth2-proxy/), [session storage](https://oauth2-proxy.github.io/oauth2-proxy/configuration/session_storage)
- **Pomerium:** the same "signed token to the door" pattern, but it also needs our own login provider for emailed codes, and its pricing wasn't found in its docs. [Pomerium docs](https://www.pomerium.com/docs)
- **Choice:** **Cloudflare Access**. It bundles the gate, the emailed code, the tunnel and a documented per-person cancellation. Its weak spots are already handled by the plan: open connections (the door closes them), no regional processing (no US-only claim), and 24-hour log retention.

## 2. The server (hosting)
Compared: **Render**, **Fly.io** and **Railway**, from their official docs and pricing pages. A plain virtual server (VPS) wasn't chosen: we would have to run and patch the operating system ourselves.

### 2.1 Comparison
| Need | Render (background worker) | Fly.io (Machine, no services) | Railway |
|---|---|---|---|
| No public address | **By design:** a background worker receives no incoming traffic. Verified: [Background workers](https://render.com/docs/background-workers), [Private services](https://render.com/docs/private-services) | Only if the config has no services section and every deploy uses `--no-public-ips`. Verified: [Configuration](https://docs.fly.io/reference/configuration/), [Services](https://docs.fly.io/networking/services) | Possible, but not recommended (below) |
| Sizes | 512 MB or 2 GB; **no 1 GB**. Verified: [Compute plans](https://render.com/docs/compute-plans) | 512 MB, 1 GB, 2 GB. Verified: [Pricing](https://docs.fly.io/about/pricing) | Usage-based ([plans](https://docs.railway.com/pricing/plans)) |
| List price, US, per month | 512 MB **$7**; 2 GB **$25**; Hobby workspace $0. From [Render pricing](https://render.com/pricing). *My own check of that page couldn't read the figures: re-check before buying.* | 1 GB **$6.70**; 2 GB (shared-cpu-2x) **$13.39**; no platform fee. Verified: [Pricing](https://docs.fly.io/about/pricing) | About $12 for 1 GB (an estimate worked out from [usage pricing](https://docs.railway.com/pricing/plans)) |
| Emergency stop | **Suspend button in the dashboard** (and API). Verified: [Suspend](https://render.com/changelog/suspend-and-resume-services-in-bulk-from-the-render-dashboard) | Command line (`fly machine stop`); a dashboard button isn't documented. **Never "suspend" on Fly:** it writes the whole memory, uploads included, to disk. Verified: [Configuration](https://docs.fly.io/reference/configuration/) | — |
| Automatic deploys off | Yes ("Off"); previews off by default; deploy one exact commit. Verified: [Deploys](https://render.com/docs/deploys), [Previews](https://render.com/docs/service-previews) | Off by default (only if we add a GitHub workflow). Verified: [Continuous deployment](https://docs.fly.io/launch/continuous-deployment-with-github-actions) | **Railway-started redeploys** we can't opt out of (host moves, security updates), each wiping in-memory sessions ([deployment reference](https://docs.railway.com/deployments/reference)) |
| App logs | Kept 7 days on Hobby; can't be switched off. Verified: [Logging](https://render.com/docs/logging) | Kept 7 days, fixed; can't be switched off; Anthropic is listed as a sub-processor for AI-assisted log analysis; Fly says request bodies are never sent to AI vendors. Verified: [Security questionnaire](https://fly.io/legal/security-questionnaire/), [Sub-processors](https://fly.io/legal/sub-processors/) | Upgrading brings back logs older than the plan shows, so they are kept longer ([logs](https://docs.railway.com/observability/logs)) |
| Swap (memory written to disk) | **Not documented** | **Switched on only by a setting** (`swap_size_mb`); the page implies, but doesn't say outright, that it's off otherwise. [Configuration](https://docs.fly.io/reference/configuration/) | — |
| Crash dumps | Not documented | Not documented | — |
| Backups without a disk | None documented (snapshots are for disks only) | None (snapshots are for volumes only) | — |
| Staff access | Not documented (the DPA binds staff to confidentiality) | Only for security or maintenance, or with consent; no customer-facing access log | Implied possible unless a HIPAA agreement is in place ([compliance](https://docs.railway.com/enterprise/compliance)) |
| DPA and certifications | DPA part of the terms; SOC 2 Type II and ISO 27001 (reports not on Hobby). [DPA](https://render.com/dpa), [Security](https://render.com/security) | DPA to sign and return; SOC 2 report only with the $99/month package. [Security questionnaire](https://fly.io/legal/security-questionnaire/) | — |
| Ease for Alex | Mostly dashboard | Mostly command line | — |

### 2.2 Recommendation: Render, background worker, 2 GB, Virginia or Ohio
- **Why:** it can't be given a public address by mistake, it has a dashboard stop button (the plan's first emergency step), deploys can be locked to one exact commit, and it's run from a dashboard Alex can use.
- **Main cost:** 2 GB at about $25 a month, the top of the plan's $5–$25 estimate, because Render has no 1 GB size and 512 MB is too small (section 3).
- **What must be confirmed before P4** (Alex sends the questions to Render support; Claude drafts them):
  - is swap ever used for a worker;
  - are crash dumps or core files ever kept;
  - do staff ever access a running service's memory.
  **If Render can't confirm, the retention gate isn't met there, and we switch to Fly.io** (swap only when set, 2 GB at $13.39), after asking Fly the same questions, and with the stricter config discipline it needs.
- **Not recommended: Railway** (forced redeploys, longer log keeping, staff-access wording).

### 2.3 Details for the later steps (none changes the design)
- **Two copies during each Render deploy:** for a short time the new copy starts before the old one stops, so two tunnel connections run at once. Verified: [Deploys](https://render.com/docs/deploys). P4 rule: deploy only when no trial user is active. The restart quarantine then applies to the new copy.
- **Secrets:** Render copies secret files into the Docker build folder, so they must be in `.dockerignore`, or they end up inside the image. Verified: [Docker secrets](https://render.com/docs/docker-secrets). Saving a secret starts a deploy by default ("Save only" exists). Verified: [Environment variables](https://render.com/docs/configure-environment-variables).
- **Tunnel protocol:** none of the hosts documents outbound UDP. Run `cloudflared --protocol http2` (TCP only) and test it in P4. Source: [Tunnel with firewall](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/).
- **Connection resets:** Render sometimes resets long outbound connections. `cloudflared` reconnects, but a user mid-session may see a reconnect. Verified: [Outbound connection resets](https://render.com/docs/outbound-connection-resets).
- **Logs can't be switched off anywhere,** so MargenX and the door must never print file contents, tokens or cookies (already in the plan, P3).


## 3. Memory measured with made-up files
Measured on 2026-10-27 on the Mac, with Python 3.11 and the pinned packages. Each figure is one Python process: MargenX's reading code, with Streamlit, pandas, openpyxl and altair loaded. The files were generated made-up data near MargenX's 50,000-line limit.

| Case | File size | Lines | Peak memory |
|---|---|---|---|
| Libraries loaded, nothing read | — | — | about 160 MB |
| Made-up CSV sales file read and checked | 4.2 MB | 49,000 | about 250 MB |
| Made-up Excel sales file read and checked | 1.9 MB | 49,000 | about 280 MB |

- **What it means:** one large file adds roughly 90–120 MB on top of the base. Add the Streamlit server, the door and `cloudflared`, and several shops at once with large files can pass 1 GB. **512 MB is too small; 2 GB is comfortable.**
- **Limits:** this is one process on a Mac, not the running server. P3 sets the total and per-session limits, and P4 measures the real container.


## 4. What changes in the later steps (details only)
| Finding | Step | What it means |
|---|---|---|
| The gate's cancellation answer only says "accepted", and it can take up to 1 minute; old tokens work for 20–30 seconds after a logout | P2 | "The gate confirms" means it accepted the cancellation. The door's refusal after a logout is **at least 2 minutes** (not 60 seconds), and a new emailed code after logout is proven in P4 (test requirement 21) |
| A cancellation isn't a ban | P5, 1d | Trial end and early end: **take the email off the allow rule first, then cancel** |
| The emailed code isn't the default | P4 | Add it; make it the app's only login method; "instant authentication" on |
| CSV and Excel files are cached by default | P4 | A "bypass cache" rule for the whole MargenX address, plus "don't store" (already planned) |
| Logout and cancellation act on the whole Cloudflare account | P4 | A **separate Cloudflare account** just for MargenX |
| The domain must be fully on Cloudflare (free plan) | Before P4 | **A separate small domain for MargenX** is recommended, so Abrey's site and email aren't touched; ask Alex and Abrey |
| The narrow "Revoke" key permission may not work on that call | P4 | Test it first; if only the broad permission works, the key is guarded like a password and kept only in Render's secret settings |
| Open connections aren't cut by Cloudflare | P2 | Confirms the door's design: the door closes them |
| Whether the DPA covers a free Cloudflare account | T | Check with Cloudflare before the trial terms are finalised |
| Render swap, crash dumps, staff access | Before P4 | Ask Render support in writing; if not confirmed, use Fly.io |
| Render runs two copies briefly at each deploy | P4, P5 | Deploy only when no trial user is active |
| Render secret files enter the Docker build folder | P3, P4 | List them in `.dockerignore` |
| Login records keep emails, and user records can't be deleted at Cloudflare | T | Say so in the privacy notice (the plan already allows for it) |

## 5. What only a live test can prove (P2, P4, F)
- After a logout or a cancellation, logging back in **needs a new emailed code**, on every device (test requirement 21).
- The narrow "Revoke" key permission works on the cancellation call.
- How long after a cancellation old tokens are refused at the gate.
- Whether an open live connection survives a cancellation at the gate (the door closes it anyway).
- Whether the free plan can change request buffering.
- The tunnel over `http2` on Render.
- The real memory of the running container.

## 6. Decisions for Alex (when we reach P0 and P4; not now)
1. **Server:** Render 2 GB (about $25/month, simpler, dashboard) or Fly.io 2 GB (about $13.39/month, command line). *Recommended: Render, if its support confirms swap, crash dumps and staff access.*
2. **Domain:** a separate small domain just for MargenX (recommended), or move our existing domain's settings to Cloudflare (touches Abrey's website and email).
3. **A separate Cloudflare account** for MargenX. *Recommended: yes.*
4. **Budget:** about $25 a month for the server, plus a domain per year. Nothing is bought before Alex approves it.

Building still waits until after the first real shop meeting (Alex, 2026-10-27).

