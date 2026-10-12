# web: odd things we keep seeing

Last updated: 2026-07-13  
Owner: Aiko (web)  

## Maintenance

This page is maintained by Aiko and the web engineering team to track quirks that recur on the web service. We write these notes down so people working secondary shifts or holding the paging tool do not spend an hour rediscovering known oddities across our regions in ap-northeast, us-east, and eu-west.

## Rare kanji rendering boxes on booking pages

Tofu on the booking page in June 2026: customer names with rare kanji (for example 髙 or 﨑) rendered as empty boxes, because the subset web font left out those glyphs. Priya added a fallback to the full Noto Sans JP font on 2026-06-11.

* The problem was particularly visible on salon and clinic confirmation screens where end users entered family names containing un-subsetted characters.
* We traced the missing characters through the browser inspection tool before realizing the asset bundle was aggressively trimmed during build steps.
* Priya patched the stylesheet stack directly to pull the wider font when the primary bundle encounters an unmapped character code.
* When you see this on call, verify whether the browser is loading the fallback font and no action is required unless a new unmapped glyph set appears outside Japanese names.

## Crawler bursts tripping traffic alerts

Search-engine crawler bursts on public business pages trip web-traffic a few times a month; they are harmless when 5xx and page load stay flat.

* Bot fleets hitting business profile directories periodically generate noticeable step increases in inbound request counts across public endpoints.
* These automated spikes regularly show up on the metrics tool during off-peak hours and sometimes trigger automated traffic thresholds on the "Sorrel / web" board.
* The web app handles the read-only rendering without stressing downstream dependencies, provided the database caches held by api absorb the tenant queries properly.
* When you see this on call, check the metrics tool to confirm error rates and response latencies remain unaffected; if metrics are healthy, take no action and log it in the shift notes.

## Safari service worker persistence after releases

Safari keeps the old service worker longer than other browsers; after a release, support can ask a customer to reload twice.

* Following a routine update using the deploy tool, we periodically hear from Hana that customers on Apple devices still run older client bundles.
* The caching layer in WebKit hangs onto active worker registrations significantly longer than Chromium or Gecko runtimes, even when lifecycle headers prompt an update.
* This discrepancy occasionally produces minor script errors or stale form behavior on the admin tool and booking panels right after fresh code lands.
* When you see this on call, point support to the known browser workaround so Hana can advise the user without escalating a bug to the team.

## Static asset invalidation via cloudflare

The cloudflare edge serves most static files; a purge normally finishes in about a minute.

* Our frontend bundle assets, icons, and public business stylesheets rely on external caching to prevent load from saturating hosting instances on aws.
* Whenever a quick hotfix goes through and stale assets linger across edge locations, clearing cache tags or URLs via cloudflare restores freshness swiftly.
* Edge nodes reliably drop their cached objects within sixty seconds, making this a predictable operation during routine asset updates.
* When you see this on call, check provider if static asset updates appear delayed across edge locations after a recent push.

-- Aiko
