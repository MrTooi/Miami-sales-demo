# Step R: hosting and login research for the website trial (issue #131)

- **Date:** 2026-10-27. **Author:** Claude Code, step R of the reviewed plan in issue #131 (plan v7, manual review PASS WITH WARNINGS).
- **What this is:** desk research from the providers' **official documentation and pricing pages** only, plus one memory measurement with made-up files. Nothing was signed up for, bought or set up. No real shop data was used.
- **What this isn't:** proof that the design works. Everything marked **To test** must be shown on a real test setup in P2 or P4, as the plan says. Prices are list prices seen on 2026-10-27; they must be checked again before anything is bought.
- **Labels:** **Verified** = the provider's own page says it plainly. **Unclear** = the page is silent or contradicts itself. **Not available** = not on the plan we'd use. **Unresolved** = a release condition that this research can't settle; it blocks real files until written provider evidence or a live test settles it. **Provisional** = a working assumption to be replaced by a measurement or a fresh price.
- Sources are links to the providers' own pages. Quotes are kept short; everything else is paraphrased.
- **Revised after the manual review of this PR (FAIL at ce7c228, 5 blockers):** the earlier draft stated the retention gate, the logout timing, the end-of-trial order, the memory size and the cost more firmly than the evidence supports. Those are now marked **Unresolved** or **Provisional**, with what would settle each one.
- **How it was checked:** two research passes read the official pages and labelled each answer. Claude then re-read the most important ones itself on 2026-10-27:
  - Cloudflare: session management (logout, cancellation, renewal, timing); the June 2026 change of the default login method; Enterprise-only WAF payload logging; the default cache list;
  - Render: that background workers receive no incoming traffic, and its worker sizes;
  - Fly.io: its prices, the swap setting, and its AI sub-processor entry.
  Render's prices couldn't be read by that re-check (the page didn't show them) and are marked so. Every other row has its link, so the reviewer can check it.

## Summary (plain words)
- **Proposed login gate: Cloudflare Access, free plan** (up to 50 users). It has the emailed code, a tunnel with no open port, and a documented "cancel this person's login everywhere" call. **We must switch on the emailed code ourselves**: since June 2026 it's no longer the default.
- **Proposed server: Render, a "background worker", in a US region.** A background worker **can't receive traffic from the internet at all**, so the only way in is the tunnel. It has a dashboard stop button, and automatic deploys can be switched off. **Fly.io** is the other candidate. **Both are conditional** (next point).
- **Three things are Unresolved, and each blocks real files until settled:**
  1. **The retention gate (no provider keeps file contents): Unresolved for Cloudflare, Render and Fly.io.** What we found lowers the risk: no body logging on Cloudflare's free plan, no bodies in its request logs, caching can be switched off, no public traffic to the server. But several provider surfaces aren't documented: memory and buffering while files pass through, security processing, internal diagnostics and crash handling, swap, and staff access. Section 1.7 and section 2.2 list them. **Written evidence from each chosen provider, surface by surface, is needed before real files.** A canary test can't replace it. If a provider can't give it, that provider can't be used for real files; if none can, real files stay off and Alex decides.
  2. **Logout: Unresolved.** The per-person cancellation exists, but Cloudflare doesn't document how long it takes to reach every device. Nothing here proves that a new emailed code is required everywhere afterwards. Section 1.4 sets a fail-closed rule for the door and what P2 and P4 must prove. If it can't be proven, the plan's fallback applies: a weaker, honestly worded logout promise, Alex's choice.
  3. **Server size and cost: Provisional.** One measurement on the Mac suggests 512 MB may be too small and 2 GB has room, but that isn't established. The real container must be measured at the worst-case workload, and prices checked fresh, before a size is chosen or anything is bought (sections 3 and 6).
- **Domain and account (proposals for Alex and Abrey, not decisions):** the free Cloudflare plan needs the **whole domain** managed by Cloudflare. A separate small domain just for MargenX would avoid touching Abrey's website and email. A separate Cloudflare account would keep logouts away from anything else.
- **Nothing found yet rules the design out.** Section 4 lists the details for the later steps; section 5 lists what only a live test or a provider's written answer can settle.

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
- **For P4:** set the overall and app sessions to match (the plan's working-day length). **That is a setting, not evidence:** while the overall session is valid, Access can quietly renew an app token. So matching lengths doesn't prove that a cancelled person must enter a new code on every device. That is proven only by the P4 test in section 1.4.

### 1.4 Logout and person-wide cancellation (the plan's logout design)
- **Per-person cancellation exists:** an API call (`POST /accounts/{account_id}/access/organizations/revoke_user`, with the email) revokes that person's Access tokens **across all apps in the account**. Verified: [revoke_user API](https://developers.cloudflare.com/api/resources/zero_trust/subresources/organizations/methods/revoke_users/), [Session management](https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/).
- **What its answer confirms:** only that the request was accepted (`"success": true`), not when every session has ended. **So in the plan, "the gate confirms" can only mean "the gate accepted the cancellation"**, and the page may say "You're logged out" only after that acceptance. Verified (response format); timing Unclear.
- **Timing (documented for other actions, not for this call):** after an administrator cancels a person in the dashboard, they can't log back in for up to 1 minute. After the logout address is visited, tokens already issued keep being accepted for 20–30 seconds. Verified: [Session management](https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/). **Neither figure is documented for the API call**, and neither says when every old token stops working. **Unclear.**
- **So the door can't rely on a fixed wait. The fail-closed rule for P2:**
  - when the gate accepts a person's cancellation, the door records a **"not before" moment** for that person. It then **refuses every token for that person issued before that moment, for as long as such a token could still be valid** (until its own expiry), not just for a few minutes;
  - **after a restart** the door has lost those records, so it refuses **every token issued before the restart** (the plan's quarantine rule), which includes every token from before any cancellation;
  - **what remains Unresolved:** a token issued after the restart, from a gate login the cancellation hasn't reached yet. The API's propagation time isn't documented. **P2 and P4 must show**, on the live setup with two devices, that after an accepted cancellation no device gets back in without a new emailed code, including across a restart. If that can't be shown, the plan's fallback applies (a weaker, honestly worded promise, Alex's choice);
  - the 2-minute quarantine stays as a **minimum** backup, not as proof.
- **A cancellation isn't a ban.** The page says a person whose identity is still active can start a new session. With emailed codes, being active likely means the email is still on the allow rule, but the page doesn't say so. Whether logging back in needs a new emailed code is **Unclear; to test** in P4 (test requirement 21), with two devices.
- **Removing someone for good (trial end, early end):** Cloudflare's page says to disable the person **at their identity provider** first, then revoke the session. Verified: [Session management](https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/). With emailed codes there's no separate identity-provider account. **Our proposed equivalent** is to take the email off the allow rule first, then cancel. **Unverified:** the page doesn't describe this, so its effect on existing tokens and on renewal must be tested in P4 before it becomes the end-of-trial procedure.
- **The logout address** (`/cdn-cgi/access/logout`) ends the person's session **in all apps of that account**. That is one more reason for **a separate Cloudflare account just for MargenX** (section 1.8). Verified: same page.
- **The narrowest key:** a "Access: Organizations Revoke" permission was added on 2026-01-22. The API page still lists the broader "Organizations, Identity Providers, and Groups Write". Whether the narrow one is accepted is **Unclear; to test** first in P4. **If only the broad permission works,** the key could change login settings. That is a bigger credential than the plan assumed, so it needs **Alex's explicit yes and a security review** before use, not just careful storage. Sources: [changelog 2026-01-22](https://developers.cloudflare.com/changelog/post/2026-01-22-granular-api-token-permissions/), [permissions](https://developers.cloudflare.com/fundamentals/api/reference/permissions/).

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

**Retention-gate verdict for Cloudflare: Unresolved.** The findings above lower the risk, but they don't establish that file contents are never persistently recorded. These surfaces aren't covered by any page found:
- the edge servers' memory while traffic is decrypted and passed on;
- request buffering ("Standard" inspects the start of a body when a security feature needs it; "Full" holds the whole body);
- security processing such as managed firewall rules and bot and DDoS protection: whether any of it keeps samples;
- internal diagnostics and crash handling on the edge servers;
- staff access.

**What would settle it:** a written statement from Cloudflare, surface by surface (a support or sales answer, or a contract or DPA clause). P4 also records the settings as set. **Practical limit:** the free plan has community support only, so getting a written answer may need a sales contact or a paid plan, an open question for Alex. Until it's settled, real files stay off (the plan's retention gate). A canary test can't settle it.

### 1.8 Domain, account and where data is processed
- **The domain must be fully on Cloudflare.** The MargenX address must be in a domain whose name servers point to Cloudflare, **in the same Cloudflare account**. A partial setup that moves only one address needs the **Business** plan, and sub-domain zones need Enterprise. Verified: [Partial setup](https://developers.cloudflare.com/dns/zone-setups/partial-setup/), [Subdomain setup](https://developers.cloudflare.com/dns/zone-setups/subdomain-setup/), [Tunnel DNS](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/routing-to-tunnel/dns/).
- **What that means for Abrey's website** (for the website questions before P4): using our existing domain would mean moving **the whole domain's** name servers to Cloudflare, which touches the website and email settings. **A separate small domain just for MargenX**, in its own Cloudflare account, avoids touching Abrey's site at all. Abrey's site would just get a "Log in" link. **A proposal**, for Alex and Abrey to decide before P4.
- **A separate Cloudflare account for MargenX** keeps logouts and cancellations (which act on the whole account) away from anything else. A proposal; Alex decides.
- **Where data is processed:** encrypted traffic is opened at whichever Cloudflare data center receives it. Keeping it in one region needs the Data Localization Suite, an **Enterprise** add-on. So **no "US-only" claim** can be made for the gate. Sources: [Data localization](https://developers.cloudflare.com/data-localization/), [Regional services](https://developers.cloudflare.com/data-localization/regional-services/).
- **Contract terms:** Cloudflare is a processor under its data processing agreement (DPA, v6.4), and the terms keep ownership of content with us. **Whether the DPA applies to a Free account without a separate step is Unclear**; to check before T. Sources: [DPA](https://www.cloudflare.com/cloudflare-customer-dpa/), [Terms](https://www.cloudflare.com/terms/).

### 1.9 Alternatives compared
- **oauth2-proxy** (run by us): a gate in front of the app, but it has **no emailed code** of its own. It needs a separate login provider, its own route in, and certificates we manage, and no cancellation API is documented. More moving parts. [oauth2-proxy](https://oauth2-proxy.github.io/oauth2-proxy/), [session storage](https://oauth2-proxy.github.io/oauth2-proxy/configuration/session_storage)
- **Pomerium:** the same "signed token to the door" pattern, but it also needs our own login provider for emailed codes, and its pricing wasn't found in its docs. [Pomerium docs](https://www.pomerium.com/docs)
- **Proposed:** **Cloudflare Access**. It bundles the gate, the emailed code, the tunnel and a documented per-person cancellation. Its weak spots are handled by the plan: the door closes open connections, there's no US-only claim, and logs are kept 24 hours. **It's still conditional** on the retention evidence (section 1.7) and the logout proof (section 1.4).

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

### 2.2 Proposed: Render, background worker, US region. Both Render and Fly.io are conditional
- **Why Render first:** it can't be given a public address by mistake, it has a dashboard stop button (the plan's first emergency step), deploys can be locked to one exact commit, and it's run from a dashboard Alex can use.
- **Neither provider passes the retention gate on paper.** Undocumented surfaces:
  - **Render:** swap, crash dumps or core files, and staff access to a running service's memory;
  - **Fly.io:** crash dumps, and whether swap is off unless set (its page only says the setting enables swap). Staff access is described as for security, maintenance or support with consent.
- **What's needed before real files:** a written answer from the chosen provider covering each of these surfaces. Claude drafts the questions; Alex sends them.
  - **If the answer covers every surface:** that provider can be used, still subject to the P4 settings check.
  - **If not:** that provider can't be used for real files. If neither can, real files stay off, and Alex decides what to do next (for example the installed-app fallback in #131).
- **Not recommended: Railway** (Railway-started redeploys, longer log keeping, staff-access wording).

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

- **What it suggests (Provisional):** one large file added roughly 90–120 MB on top of the base in this one test. Several shops at once with several large files, plus the Streamlit server, the door and `cloudflared`, **could** pass 512 MB, and 2 GB **likely** has room. **Neither is established.**
- **Limits:** this is one process on a Mac, reading one file. It isn't the running container, it doesn't include several sessions or four files per session, and it didn't measure the door, the tunnel or the server overhead.
- **The assumed worst-case workload for P3 and P4** (the plan's own proposed limits): up to 10 sessions in total and 3 per person, each with up to 4 files of up to 5 MB (20 MB per session), each file within the 50,000-line limit, plus the door and `cloudflared`.
- **Before a size is chosen:** P3 enforces those limits, and P4 measures the real container at that worst case. It also checks what happens when memory runs out: the service must stop or refuse safely, not lose a session's data to another session. Only then is a size, and so a price, chosen.


## 4. What changes in the later steps (details only)
| Finding | Step | What it means |
|---|---|---|
| The cancellation answer only means "accepted"; propagation time for the API isn't documented | P2, P4 | The fail-closed "not before" rule and the restart rule (section 1.4); "You're logged out" only after acceptance; P2 and P4 prove a new emailed code on every device, or the weaker promise applies |
| A cancellation isn't a ban; Cloudflare's documented order is "disable at the identity provider, then revoke" | P4, P5 | Our proposed equivalent, "remove from the allow rule, then cancel", is **Unverified**: test its effect on existing tokens and renewal before it becomes the end-of-trial procedure |
| The emailed code isn't the default | P4 | Add it; make it the app's only login method; "instant authentication" on |
| CSV and Excel files are cached by default | P4 | A "bypass cache" rule for the whole MargenX address, plus "don't store" (already planned) |
| Logout and cancellation act on the whole Cloudflare account | Before P4 | Proposal: a **separate Cloudflare account** just for MargenX (Alex decides) |
| The domain must be fully on Cloudflare (free plan) | Before P4 | Proposal: **a separate small domain for MargenX**, so Abrey's site and email aren't touched (Alex and Abrey decide) |
| The narrow "Revoke" key permission may not work on that call | P4 | Test it first. If only the broad permission works, it needs Alex's explicit yes and a security review before use |
| Open connections aren't cut by Cloudflare | P2 | Confirms the door's design: the door closes them |
| Whether the DPA covers a free Cloudflare account | T | Check with Cloudflare before the trial terms are finalised |
| Undocumented retention surfaces at Cloudflare, Render and Fly.io | Before P4, F | Written provider evidence, surface by surface; otherwise that provider isn't used for real files |
| Render runs two copies briefly at each deploy | P4, P5 | Deploy only when no trial user is active |
| Render secret files enter the Docker build folder | P3, P4 | List them in `.dockerignore`; test that no secret is inside the built image |
| Login records keep emails, and user records can't be deleted at Cloudflare | T | Say so in the privacy notice (the plan already allows for it) |

## 5. What only a live test or a provider's written answer can settle (before real files)
- **Retention, in writing:** each chosen provider's answer for every surface in sections 1.7 and 2.2.
- **Logout:** after an accepted cancellation, no device gets back in without a new emailed code, including across a restart (test requirement 21). Also how long after a cancellation old tokens are refused at the gate.
- **Removal:** "remove from the allow rule, then cancel" works on existing tokens and on renewal.
- The narrow "Revoke" key permission works on the cancellation call.
- Whether an open live connection survives a cancellation at the gate (the door closes it anyway).
- Whether the free plan can change request buffering.
- The tunnel over `http2` on the chosen host.
- **Memory:** the real container at the worst-case workload, and what happens when memory runs out.
- **Prices:** fresh prices on the day of purchase.

## 6. Decisions for Alex (when we reach P0 and P4; not now)
1. **Server:** Render or Fly.io, **only if its written retention answers cover every surface**. *Proposed: Render first, because it's run from a dashboard and can't be made public by mistake.*
2. **Domain:** a separate small domain just for MargenX, or move our existing domain's settings to Cloudflare (that touches Abrey's website and email). *Proposal; Alex and Abrey decide.*
3. **A separate Cloudflare account** for MargenX. *Proposal; Alex decides.*
4. **Getting Cloudflare's written answers:** the free plan has community support only, so Alex may need a sales contact or a paid plan to get them.
5. **Budget (Provisional; nothing is bought on it).** Its parts, with list prices seen on 2026-10-27:

   | Part | Render | Fly.io |
   |---|---|---|
   | Server | 512 MB $7 or 2 GB $25 a month ([pricing](https://render.com/pricing); not re-read by Claude) | 1 GB $6.70 or 2 GB $13.39 a month ([pricing](https://docs.fly.io/about/pricing)) |
   | Account or workspace fee | Hobby $0 (Pro $25 a month if ever needed) | None |
   | Outbound traffic | 5 GB a month included, then $0.15 per GB | $0.02 per GB from North America |
   | Builds | 500 build minutes a month included | — |
   | Taxes | not stated | not stated |

   The outbound-traffic and build figures come from the research pass ([Render FAQ](https://render.com/docs/faq), [Fly.io pricing](https://docs.fly.io/about/pricing)); Claude didn't re-read them.

   Plus the domain (paid yearly, price to check), Cloudflare $0 for up to 50 users, and possibly the cost of getting Cloudflare's written answers. **The size, and so the server price, is chosen only after P4's container measurement**, with fresh prices on the day.


Building still waits until after the first real shop meeting (Alex, 2026-10-27).

