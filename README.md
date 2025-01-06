# Toshiba/Dynabook drivers mirror

This repository hosts the software I've written to scrape and mirror
the [Dynabook support](https://support.dynabook.com/) website, as well as its front-end.

The mirror should be online [here](https://toshiba-mirror.depau.gay)

On Dynabook's website, many drivers are missing. This mirror brings the vast majority of them back by finding them on
the [Internet Archive](https://archive.org) and the [Wayback Machine](https://web.archive.org).

This website also allows you to bulk-download all drivers.

## The scraper

> [!WARNING]
> ### ⚠️⚠️⚠️ Spaghetti alert ⚠️⚠️⚠️
> This repo contains the spaghettiest Python code I've ever written. Don't look at it too closely.
>
> It also hosts horrible JavaScript written by someone who hates doing front-end and has zero front-end experience.

I initially intended this scraper to be re-usable, but the amount of time it takes to fully scan the Dynabook website
and the effort that is needed to process the data makes it not worth it.

I tried to make the scraper work in many separate steps to make it easier to debug and make manual interventions if
needed.

The scraper is written in Python, it's heavily asynchronous, and it requires [uv](https://docs.astral.sh/uv/) and
[deno](https://deno.land/) to run.

### Scraping steps

First of all, download the following files from my mirror to speed up your process.

- [potential_results.json](https://toshiba-mirror.depau.gay/potential_results.json) - Mapping from filename to Internet
  Archive upload/archive content URL, built manually mostly by searching online `toshiba drivers site:archive.org`
- [memento_cache.json](https://toshiba-mirror.depau.gay/memento_cache.json) - Cache of the Memento API responses, built
  by running the scraper
- [search_cache.json](https://toshiba-mirror.depau.gay/search_cache.json) - Cache of automated DuckDuckGo performed by
  the scraper (DDG rate-limits like crazy so you definitely want this)

Place them in your data directory.

Then, run the following commands:

```bash
export DATA_DIR=/path/to/data_dir

uv run dynabook-scrape-products-list        # Fetch the full list of products
uv run dynabook-scrape-assets               # Fetch images used by products
uv run dynabook-scrape-products-html        # Download the HTML of each product
uv run dynabook-parse-products-html         # Parse the HTML, outputting temporary JSON files
uv run dynabook-scrape-driver-contents      # Fetch details about drivers listed by products
uv run dynabook-scrape-kb-contents          # Fetch details about knowledge base articles listed by products
uv run dynabook-scrape-manuals-contents     # Fetch details about manuals/specs listed by products
uv run dynabook-scrape-content-links        # Fetch details about content linked by previously fetched content
uv run dynabook-download-contents           # Actually download the content (drivers, manuals, etc.)
uv run dynabook-download-broken-links       # Try to find broken downloads on public archives
uv run dynabook-gen-products-index          # Generate product page payloads
uv run dynabook-build-frontend              # Build the frontend templates
uv run dynabook-gen-sitemap                 # Generate a sitemap

# and finally, to build the search indices
deno --allow-env --allow-read --allow-write buildSearchIndex.deno.js
```

## Creating your own mirror

You're probably better off downloading my own mirror and hosting it yourself instead of running the scraper.

If you'd like to do that, contact me. Or don't, it should be pretty easy to figure out, the directory listings are
enabled on the web server.

The full mirror is about 391GB in size:

![image](https://github.com/user-attachments/assets/70ac7177-d851-4263-959f-af0c2dff2ad5)

## License

The software (scraper and frontend) is licensed under the MIT License.

The content (drivers, manuals, etc.) is copyrighted by Dynabook/Toshiba and is used under fair use. A copy of their
EULA is [available here](https://toshiba-mirror.depau.gay/eula/).
