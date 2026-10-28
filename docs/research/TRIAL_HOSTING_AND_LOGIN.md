# Step R: hosting and login research for the website trial (issue #131)

- **Date:** 2026-10-27. **Author:** Claude Code, step R of the reviewed plan in issue #131 (plan v7, manual review PASS WITH WARNINGS).
- **What this is:** desk research from the providers' **official documentation and pricing pages** only, plus one memory measurement with made-up files. Nothing was signed up for, bought or set up. No real shop data was used.
- **What this isn't:** proof that the design works. Everything marked **To test** must be shown on a real test setup in P2 or P4, as the plan says. Prices are list prices seen on 2026-10-27; they must be checked again before anything is bought.
- **Labels:** **Verified** = the provider's own page says it plainly. **Unclear** = the page is silent or contradicts itself. **Not available** = not on the plan we'd use. **Unresolved** = a release condition that this research can't settle; it blocks real files until written provider evidence or a live test settles it. **Provisional** = a working assumption to be replaced by a measurement or a fresh price.
- Sources are links to the providers' own pages. Quotes are kept short; everything else is paraphrased.
- **Revised twice after the manual reviews of this PR.**
  - **Round 1** (FAIL at ce7c228, 5 blockers): the retention gate, the logout timing, the end-of-trial order, the memory size and the cost had been stated more firmly than the evidence supports. They are now **Unresolved** or **Provisional**, with what would settle each one.
  - **Round 2** (FAIL at db09d41, 2 blockers): the hosting retention inventory was incomplete, and where each host processes data was missing. Sections 2.2 and 2.4 now cover both.
- **How it was checked:** two research passes read the official pages and labelled each answer. Claude then re-read the most important ones itself on 2026-10-27:
  - Cloudflare: session management (logout, cancellation, renewal, timing); the June 2026 change of the default login method; Enterprise-only WAF payload logging; the default cache list;
  - Render: that background workers receive no incoming traffic, and its worker sizes;
  - Fly.io: its prices, the swap setting, and its AI sub-processor entry.
  Render's prices couldn't be read by that re-check (the page didn't show them) and are marked so. Every other row has its link, so the reviewer can check it.

## Summary (plain words)
- **Proposed login gate: Cloudflare Access, free plan** (up to 50 users). It has the emailed code, a tunnel with no open port, and a documented "cancel this person's login everywhere" call. **We must switch on the emailed code ourselves**: since June 2026 it's no longer the default.
- **Proposed server: Render, a "background worker", in a US region.** A background worker **can't receive traffic from the internet at all**, so the only way in is the tunnel. It has a dashboard stop button, and automatic deploys can be switched off. **Fly.io** is the other candidate. **Both are conditional** (next point).
- **Three things are Unresolved, and each blocks real files until settled:**
  1. **The retention gate (no provider keeps file contents): Unresolved for Cloudflare, Render and Fly.io.** Some findings lower the risk:
     - Cloudflare's customer-configurable WAF payload logging isn't available on the free plan;
     - its request-log fields have no body field;
     - caching can be switched off for the address;
     - the server gets no public traffic.
     None of that shows a provider keeps nothing. Many surfaces aren't documented: memory and buffering while files pass through, security processing and telemetry, temporary files, diagnostics and crash handling, swap, and staff access. Section 1.7 lists them for Cloudflare and section 2.2 for each host. **Before real files, each chosen provider must give written evidence that uploaded contents aren't persistently recorded in any of them.** A canary test can't replace it. If a provider can't, it can't be used for real files; if none can, real files stay off and Alex decides.
  2. **Logout: Unresolved, and tests alone can't settle it.** The per-person cancellation exists, but Cloudflare doesn't document how long it takes to reach every device. A two-device test can't rule out the timing gap where an old gate login gets a new app token. **The strong promise ("a new emailed code on every device") stays blocked** until there is either Cloudflare's documented or written limit on that timing, or a mechanism that forces a fresh emailed code regardless of it (section 1.4). Otherwise, before release, Alex must explicitly approve the plan's weaker, honestly worded promise, and the guide and terms must change to match.
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
- **For P4:** set the overall and app sessions to match (the plan's working-day length). **That is a setting, not evidence:** while the overall session is valid, Access can quietly renew an app token. So matching lengths doesn't prove that a cancelled person must enter a new code on every device. That needs section 1.4's (a) or (b); a test alone can't prove it.

### 1.4 Logout and person-wide cancellation (the plan's logout design)
- **Per-person cancellation exists:** an API call (`POST /accounts/{account_id}/access/organizations/revoke_user`, with the email) revokes that person's Access tokens **across all apps in the account**. Verified: [revoke_user API](https://developers.cloudflare.com/api/resources/zero_trust/subresources/organizations/methods/revoke_users/), [Session management](https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/).
- **What its answer confirms:** only that the request was accepted, not when every session has ended. The answer has both a `success` field and a `result` field; **P2 treats a cancellation as accepted only when both are true and the request returned normally**. An HTTP 200 or `success` alone isn't enough, and an error or timeout counts as not accepted. In the plan, "the gate confirms" therefore means "the gate accepted the cancellation", and the page may say "You're logged out" only after that. Verified: [revoke_user API](https://developers.cloudflare.com/api/resources/zero_trust/subresources/organizations/methods/revoke_users/) (response fields); timing Unclear.
- **Timing (documented for other actions, not for this call):** after an administrator cancels a person in the dashboard, they can't log back in for up to 1 minute. After the logout address is visited, tokens already issued keep being accepted for 20–30 seconds. Verified: [Session management](https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/). **Neither figure is documented for the API call**, and neither says when every old token stops working. **Unclear.**
- **So the door can't rely on a fixed wait. The fail-closed rule for P2:**
  - when the gate accepts a person's cancellation, the door records a **"not before" moment** for that person. It then **refuses every token for that person issued before that moment, for as long as such a token could still be valid** (until its own expiry), not just for a few minutes;
  - **after a restart** the door has lost those records, so it refuses **every token issued before the restart** (the plan's quarantine rule), which includes every token from before any cancellation;
  - **what remains Unresolved:** a token issued after the cancellation or after a restart, from a gate login the cancellation hasn't reached yet. Such a token passes both rules above. The API's propagation time isn't documented, and **a sampled test, even on two devices, can't show that this gap never happens.** So the strong promise needs one of:
    - (a) Cloudflare's documented, or written, maximum time for a cancellation to reach every session, which the door then waits out fail-closed;
    - (b) a mechanism that forces a fresh emailed code whatever the timing. Candidates for P2 to check: a token field showing when the person last entered a code; or briefly taking the email off the allow rule during the cancellation, so no renewal can pass (this is the unverified "remove, then cancel" order, which P4 must test).
    If neither is shown, **Alex must explicitly approve the weaker promise before release** (Log out closes MargenX on this browser; the login itself ends when its set time runs out), and the guide and terms change to match. P2 and P4 still test two devices and restarts, but as checks, not as proof.
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
| List price, US, per month | 512 MB **$7**; 2 GB **$25**; Hobby workspace $0. From [Render pricing](https://render.com/pricing). *My own check of that page couldn't read the figures: re-check before buying.* | 1 GB **$6.70**; 2 GB (shared-cpu-2x) **$13.39**; no platform fee. These are for the cheapest US regions (Ashburn `iad`, Secaucus `ewr`) and 30 days of continuous running. Verified: [Pricing](https://docs.fly.io/about/pricing) | About $12 for 1 GB (an estimate worked out from [usage pricing](https://docs.railway.com/pricing/plans)) |
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
- **Neither host passes the retention gate on paper.** The full inventory of places an uploaded file could end up on each host is below, with what is documented and what evidence is still needed.
- **Acceptance rule (the plan's retention gate):** a host can be used for real files only with **written evidence that establishes that uploaded contents aren't persistently recorded in any surface below**. That evidence is the provider's own documents or a written answer from them, plus P3/P4 checks of what MargenX itself does. An answer that merely "covers every surface" isn't enough.
- **If a host doesn't meet the rule:** that host can't be used for real files. If neither can, real files stay off, and Alex decides what to do next (for example the installed-app fallback in #131). Claude drafts the questions; Alex sends them.

**The retention inventory for the hosts:**

| Surface | Render: documented | Fly.io: documented | Still needed (both) |
|---|---|---|---|
| Process memory while a session runs | The file is there by design (in memory only, as the plan says) | Same | P3: limits; P4: memory exhaustion fails safely |
| Swap (memory written to disk) | Not documented | Switched on only by `swap_size_mb`; that it's off otherwise is implied, not stated ([Configuration](https://docs.fly.io/reference/configuration/)) | Written answer: is swap ever used, and where |
| Root and temporary filesystem | **Ephemeral but writable:** local changes are lost only at a restart or redeploy, so anything written stays until then ([Disks](https://render.com/docs/disks)) | Rebuilt fresh from the image when a Machine stops ([Scale count](https://docs.fly.io/launch/scale-count)); what happens to it before then isn't stated | P3: prove MargenX, Streamlit, pandas and openpyxl write **no** temporary or spill files with contents. Written answer: is the ephemeral disk ever copied, kept or reused |
| App logs (stdout and stderr) | Kept 7 days on Hobby; can't be switched off ([Logging](https://render.com/docs/logging)) | Kept 7 days, fixed; can't be switched off ([Security questionnaire](https://fly.io/legal/security-questionnaire/)) | P3: MargenX and the door never print contents, tokens or cookies (the canary test) |
| Platform request and proxy logs | Logged for public web services only (method, status, address); a worker has no public traffic ([Logging](https://render.com/docs/logging)) | Proxy logs; none for an app with no services, as no traffic goes through the proxy ([Security questionnaire](https://fly.io/legal/security-questionnaire/)) | P4: confirm no such log exists for our service |
| Metrics | Not documented | Kept about 15 days ([Security questionnaire](https://fly.io/legal/security-questionnaire/)) | Written answer: metrics hold no contents (expected: counts only) |
| Security monitoring and telemetry | Not documented | **A separate security pipeline with "significantly longer retention"**: fleet and application telemetry, host runtime detection, in AWS OpenSearch and object storage; retention period not stated ([Security questionnaire](https://fly.io/legal/security-questionnaire/)) | Written answer: does any security or runtime monitoring capture file or memory contents, and for how long |
| Host diagnostics, crash dumps, core files | Not documented | Not documented | Written answer: are crash dumps or core files ever made or kept for a service |
| Memory snapshots | None documented | **"Suspend" writes the whole memory to disk**; it's only used if we choose it, so it must never be used ([Configuration](https://docs.fly.io/reference/configuration/), [Security questionnaire](https://fly.io/legal/security-questionnaire/)) | P4: suspend never configured (Fly) |
| Backups and snapshots | Daily snapshots only for persistent disks; we attach none ([Disks](https://render.com/docs/disks)) | Daily snapshots only for volumes; we attach none ([Security questionnaire](https://fly.io/legal/security-questionnaire/)) | P4: no disk or volume attached |
| Build artifacts and images | Builds kept for rollback (5 on Hobby); they hold code, not shop files. **Secret files can enter the image** ([Docker secrets](https://render.com/docs/docker-secrets)) | Images kept; code, not shop files | P3/P4: no secret in any image layer |
| Staff and support access | Not documented beyond confidentiality in the DPA | For security or maintenance, or support with consent; logged internally, not shown to customers ([Privacy policy](https://fly.io/legal/privacy-policy), [Security questionnaire](https://fly.io/legal/security-questionnaire/)) | Written answer: can staff read a running service's memory or disk, and is it recorded |

- **Not recommended: Railway** (Railway-started redeploys, longer log keeping, staff-access wording).

### 2.3 Details for the later steps (none changes the design)
- **Two copies during each Render deploy:** for a short time the new copy starts before the old one stops, so two tunnel connections run at once. Verified: [Deploys](https://render.com/docs/deploys). P4 rule: before a deploy, the door stops new logins and drains existing sessions; then the deploy runs. The restart quarantine then applies to the new copy.
- **Secrets:** Render copies secret files into the Docker build folder, so they must be in `.dockerignore`, or they end up inside the image. Verified: [Docker secrets](https://render.com/docs/docker-secrets). Saving a secret starts a deploy by default ("Save only" exists). Verified: [Environment variables](https://render.com/docs/configure-environment-variables).
- **Tunnel protocol:** none of the hosts documents outbound UDP. Run `cloudflared --protocol http2` (TCP only) and test it in P4. Source: [Tunnel with firewall](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/).
- **Connection resets:** Render sometimes resets long outbound connections. `cloudflared` reconnects, but a user mid-session may see a reconnect. Verified: [Outbound connection resets](https://render.com/docs/outbound-connection-resets).
- **Logs can't be switched off anywhere,** so MargenX and the door must never print file contents, tokens or cookies (already in the plan, P3).

### 2.4 Where each host processes data
"US region" only says where the app runs. Logs, telemetry, control systems, backups and staff access can be elsewhere.

| What | Render | Fly.io |
|---|---|---|
| The app itself (where shop files are read) | The region we pick: Oregon, Ohio or Virginia; it can't be changed later ([Regions](https://render.com/docs/regions)) | The region we pick, e.g. Ashburn or Secaucus; app data "stays in the regions you deploy to" ([Security questionnaire](https://fly.io/legal/security-questionnaire/)) |
| Logs and metrics | Where they are stored isn't stated. The sub-processors listed are all US entities (AWS, Google Cloud, Cloudflare, ClickHouse), which suggests the US but doesn't prove it ([Security](https://render.com/security)) | **Processed in the US**, whatever the app's region (platform logs, metrics, proxy traces, image builds) ([Security questionnaire](https://fly.io/legal/security-questionnaire/)) |
| Control systems (accounts, settings, secrets) | Not stated | Held in the US ([Security questionnaire](https://fly.io/legal/security-questionnaire/)) |
| Security monitoring | Not stated | AWS OpenSearch and object storage; region not stated ([Security questionnaire](https://fly.io/legal/security-questionnaire/)) |
| Backups | None for us (no disk) | None for us (no volume). Volume snapshots would be in AWS us-east-1 ([Security questionnaire](https://fly.io/legal/security-questionnaire/)) |
| Staff and support access | Not stated | A **"globally distributed team"**; no country list; no access from sanctioned countries ([Security questionnaire](https://fly.io/legal/security-questionnaire/)) |
| Contract (DPA) location wording | The research pass read Render's DPA as saying primary processing is in the US. **Claude's re-check couldn't read that page's text**, so this is unconfirmed ([DPA](https://render.com/dpa)) | DPA from the Trust Center, signed and returned ([Security questionnaire](https://fly.io/legal/security-questionnaire/)) |
| The login gate in front | Cloudflare decrypts traffic wherever its network receives it; no regional option on the free plan (section 1.8) | Same |

- **For the questions to the providers:** Render: where logs, metrics, diagnostics and control data are stored, and where staff and support can access from. Fly.io: the security pipeline's region and retention.
- **For step T:** the privacy notice describes these locations as documented, with the unknowns as unknowns. It never says "US-only" unless every row is confirmed. Staff access from other countries (Fly.io's wording) and Cloudflare's worldwide edge mean an international-processing statement is likely needed.

## 3. Memory measured with made-up files
Measured on 2026-10-27 on the Mac, with Python 3.11 and the pinned packages. Each figure is one Python process: MargenX's reading code, with Streamlit, pandas, openpyxl and altair loaded. The files were generated made-up data near MargenX's 50,000-line limit.

| Case | File size | Lines | Peak memory |
|---|---|---|---|
| Libraries loaded, nothing read | — | — | about 157–162 MB |
| Made-up CSV sales file read and checked | 4.2 MB | 49,000 | about 251–272 MB (two runs) |
| Made-up Excel sales file read and checked | 1.9 MB | 49,000 | about 277–283 MB (two runs) |

- **How:** the script and its output are in the appendix at the end, so anyone can re-run it.
- **What it suggests (Provisional):** one large file added roughly 90–125 MB on top of the base in these runs, and the figures vary between runs. Several shops at once with several large files, plus the Streamlit server, the door and `cloudflared`, **could** pass 512 MB, and 2 GB **likely** has room. **Neither is established.**
- **Limits:** this is one process on a Mac, reading one file. It isn't the running container, it doesn't include several sessions or four files per session, and it didn't measure the door, the tunnel or the server overhead.
- **The assumed worst-case workload for P3 and P4** (the plan's own proposed limits): up to 10 sessions in total and 3 per person, each with up to 4 files of up to 5 MB (20 MB per session), each file within the 50,000-line limit, plus the door and `cloudflared`.
- **Before a size is chosen:** P3 enforces those limits, and P4 measures the real container at that worst case. It also checks what happens when memory runs out: the service must stop or refuse safely, not lose a session's data to another session. Only then is a size, and so a price, chosen.


## 4. What changes in the later steps (details only)
| Finding | Step | What it means |
|---|---|---|
| The cancellation answer only means "accepted"; propagation time for the API isn't documented | P2, P4 | The fail-closed "not before" rule and the restart rule (section 1.4); "You're logged out" only after acceptance (both `success` and `result` true). The strong promise needs a documented or written maximum time, or a forced fresh code (section 1.4 (a) or (b)); otherwise Alex explicitly approves the weaker promise before release. Tests are checks, not proof |
| A cancellation isn't a ban; Cloudflare's documented order is "disable at the identity provider, then revoke" | P4, P5 | Our proposed equivalent, "remove from the allow rule, then cancel", is **Unverified**: test its effect on existing tokens and renewal before it becomes the end-of-trial procedure |
| The emailed code isn't the default | P4 | Add it; make it the app's only login method; "instant authentication" on |
| CSV and Excel files are cached by default | P4 | A "bypass cache" rule for the whole MargenX address, plus "don't store" (already planned) |
| Logout and cancellation act on the whole Cloudflare account | Before P4 | Proposal: a **separate Cloudflare account** just for MargenX (Alex decides) |
| The domain must be fully on Cloudflare (free plan) | Before P4 | Proposal: **a separate small domain for MargenX**, so Abrey's site and email aren't touched (Alex and Abrey decide) |
| The narrow "Revoke" key permission may not work on that call | P4 | Test it first. If only the broad permission works, it needs Alex's explicit yes and a security review before use |
| Open connections aren't guaranteed to be cut by Cloudflare (undocumented) | P2 | Confirms the door's design: the door closes them |
| Whether the DPA covers a free Cloudflare account | T | Check with Cloudflare before the trial terms are finalised |
| Undocumented retention surfaces at Cloudflare, Render and Fly.io | Before P4, F | Written provider evidence, surface by surface; otherwise that provider isn't used for real files |
| Render runs two copies briefly at each deploy | P4, P5 | Before a deploy, the door stops letting anyone new in and closes existing sessions (a drain), then the deploy runs. Watching for "no active users" alone leaves a race while two copies run |
| Render secret files enter the Docker build folder | P3, P4 | List them in `.dockerignore`; test that no secret is inside the built image |
| Login records keep emails, and user records can't be deleted at Cloudflare | T | Say so in the privacy notice (the plan already allows for it) |

## 5. What only a live test or a provider's written answer can settle (before real files)
- **Retention, in writing:** each chosen provider's answer for every surface in sections 1.7 and 2.2.
- **Logout:** a documented or written maximum cancellation time from Cloudflare, or a mechanism that forces a fresh emailed code (section 1.4 (a) or (b)). Two-device and restart tests in P2 and P4 are checks, not proof. Without (a) or (b), Alex's explicit approval of the weaker promise is required before release.
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
   | Server | 512 MB $7 or 2 GB $25 a month ([pricing](https://render.com/pricing); not re-read by Claude) | 1 GB $6.70 or 2 GB $13.39 a month, in Ashburn or Secaucus, running all 30 days ([pricing](https://docs.fly.io/about/pricing)) |
   | Account or workspace fee | Hobby $0 (Pro $25 a month if ever needed) | None |
   | Outbound traffic | 5 GB a month included, then $0.15 per GB | $0.02 per GB from North America |
   | Builds | 500 build minutes a month included | — |
   | Taxes | not stated | not stated |

   The outbound-traffic and build figures come from the research pass ([Render FAQ](https://render.com/docs/faq), [Fly.io pricing](https://docs.fly.io/about/pricing)); Claude didn't re-read them.

   Plus the domain (paid yearly, price to check), Cloudflare $0 for up to 50 users, and possibly the cost of getting Cloudflare's written answers. **The size, and so the server price, is chosen only after P4's container measurement**, with fresh prices on the day.


Building still waits until after the first real shop meeting (Alex, 2026-10-27).

## Appendix: how the memory was measured
Run from the repository root, with the project's Python setup. The script makes its own **made-up** files; it reads no real data.

```bash
for case in base csv xlsx; do python -I measure.py "$PWD" "$case"; done
```

`measure.py`:

```python
"""Peak memory of one Python process reading made-up MargenX files (no real data)."""
import io, resource, sys, random, os
sys.path.insert(0, sys.argv[1])
scenario = sys.argv[2]
def peak_mb():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 1e6 if sys.platform == "darwin" else r / 1e3
import streamlit, pandas, openpyxl, altair  # what the app loads
import job_intake as ji, job_profit
base = peak_mb()
def made_up_csv(n):
    rnd = random.Random(7); out = io.StringIO()
    out.write("Invoice #,Date,Customer Name,Job No,Description,Total\n")
    for i in range(n):
        out.write(f"FIC-{i},10/{rnd.randint(1,28):02d}/2026,Example Customer {i%300} (fictional),J-{i%2000},Made-up item {i},{rnd.randint(50,5000)}.{rnd.randint(0,99):02d}\n")
    return out.getvalue().encode()
def made_up_xlsx(n):
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Invoice #","Date","Customer Name","Job No","Description","Total"])
    rnd = random.Random(7)
    for i in range(n):
        ws.append([f"FIC-{i}", f"10/{rnd.randint(1,28):02d}/2026", f"Example Customer {i%300} (fictional)", f"J-{i%2000}", f"Made-up item {i}", rnd.randint(50,5000)+rnd.randint(0,99)/100])
    b = io.BytesIO(); wb.save(b); return b.getvalue()
n = 49_000
data = made_up_csv(n) if scenario == "csv" else made_up_xlsx(n) if scenario == "xlsx" else None
if data is None:
    print(f"baseline peak {base:.0f} MB"); sys.exit()
before = peak_mb()
headers, records, notes = ji.read_file("made_up." + scenario, data)
kind = ji.detect_kind(headers) or "invoices"
mapping = ji.suggest_mapping(headers, kind)
try:
    fmt = ji.suggest_date_format(ji.column_values(headers, records, mapping["date"]))
    res = ji.intake(headers, records, mapping, kind, fmt, "line", {})
    ok = f"intake done: {getattr(res,'accepted',None) if isinstance(getattr(res,'accepted',None),int) else len(getattr(res,'accepted',[]) or [])} accepted"
except Exception as e:
    ok = f"intake not run ({type(e).__name__}: {str(e)[:80]})"
print(f"{scenario}: {len(data)/1e6:.1f} MB file, {len(records)} rows, peak {peak_mb():.0f} MB (baseline {base:.0f} MB), {ok}")
```

Output on 2026-10-27 (macOS, Python 3.11; `ru_maxrss` is the process's peak resident memory):

```text
baseline peak 157 MB
csv: 4.2 MB file, 49000 rows, peak 272 MB (baseline 160 MB), intake done: 49000 accepted
xlsx: 1.9 MB file, 49000 rows, peak 283 MB (baseline 159 MB), intake done: 48074 accepted
```
