# MkDocs

This documentation page was generated using the `mkdocs` package, which allows the generation of these pages using only `.md` files which is extremely useful.

## File Layout
    docs-src/
        mkdocs.yml    # The configuration file.
        docs/
            index.md  # The documentation homepage.
            ...       # Other markdown pages, images and other files.

## How to Make Changes

The `mkdocs.yml` file defines a few things, but most importantly:

* `site_url`, which MUST match the current domain the application is hosted (if hosted at all) and the endpoint, `/docs`.
* `nav`, which defines the options at the top bar of the page and what markdown files they should point to.

If you want to add pages or change orders, paths of files, etc, manipulate the options in `nav`.

To learn markdown syntax, use the current documentation files or reference [this nice guide](https://www.markdownguide.org/basic-syntax/).

Once any changes are made, mkdocs needs to create the static pages from the markdown documents. This process is automated if [running with Docker](./index.md#running-via-docker-commands), but if [running with Python](./index.md#running-via-python-commands), run:

`mkdocs build -f docs-src/mkdocs.yml -d ../static/documentation`
