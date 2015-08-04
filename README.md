# chicago-openelex
Chicago Open Election Scraper

To run:

1. set up [openelections-core](https://github.com/openelections/openelections-core)
2. set up this repo
  ```
  git clone git@github.com:datamade/chicago-openelex.git
  cd chicago-openelex
  python setup.py develop
  ```

3. run the scraper
  ```
  openelex scrape --state=il --place=chicago
  ```
