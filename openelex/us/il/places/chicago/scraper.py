import scrapelib
import lxml.html
import os
import json
import re
from dateutil.parser import parse
import requests

class Scraper(scrapelib.Scraper):
    def __init__(   self,
                    raise_errors=True,
                    requests_per_minute=100,
                    follow_robots=True,
                    retry_attempts=3,
                    retry_wait_seconds=2,
                    header_func=None,
                    url_pattern=None,
                    string_on_page=None ):

        super(Scraper, self).__init__(  raise_errors=raise_errors,
                                        requests_per_minute=requests_per_minute,
                                        retry_attempts=retry_attempts,
                                        retry_wait_seconds=retry_wait_seconds,
                                        header_func=header_func )

        self.base_url = 'http://www.chicagoelections.com/'

        cache_dir = '.cache'
        self.cache_storage = scrapelib.FileCache(cache_dir)
    
    def election_urls(self):
        start_url = self.base_url + 'en/election3.asp'

        r = self.get(start_url)
        tree = lxml.html.fromstring(r.text)

        elec_options = tree.xpath("//table[@class='maincontent']//select/option/@value")
        for elec_name in elec_options:
            print 'ELECTION', elec_name
            post_data = {
                'D3' : elec_name,
                'flag1' : '1',
                'B1' : 'View'
                }
            
            contests = []

            _, result = self.urlretrieve(start_url, method='POST', body=post_data)
            tree = lxml.html.fromstring(result.text)
            contest_options = tree.xpath("//table[@class='maincontent']//select/option/@value")
            for contest_name in contest_options:
                post_data = {
                    'D3' : contest_name,
                    'flag' : '1',
                    'B1' : '  View The Results   '
                    }

                try:
                    _, result = self.urlretrieve(result.url, method='POST', body=post_data)
                    contest_urls = []
                    ballots_cast = None
                    registered_voters = None

                    try:
                        tree = lxml.html.fromstring(result.text)
                        links = tree.xpath("//table//tr//td[1]//a")
                        if 'REGISTERED VOTERS - TOTAL' in contest_name:
                            registered_voters = [(link.text, self.base_url+'en/'+link.attrib['href']) for link in links]
                        elif 'BALLOTS CAST - TOTAL' in contest_name:
                            ballots_cast = [(link.text, self.base_url+'en/'+link.attrib['href']) for link in links]
                        else:
                            for link in links:
                                contest_urls.append((link.text, self.base_url+'en/'+link.attrib['href']))
                            contests.append((contest_name, contest_urls))
                    except:
                        # TO DO - figure out what's going on here
                        print "*** ERROR: UNABLE TO PARSE HTML ***"
                        print "SKIPPING CONTEST: %s" % contest_name
                        print "request url: %s" % result.url
                        print "request post data: %s" %post_data
                        print "***********************************\n"

                except:
                    print "*** ERROR: UNABLE TO RETRIEVE RESULT ***"
                    print "SKIPPING CONTEST: %s" % contest_name
                    print "request url: %s" % result.url
                    print "request post data: %s" %post_data
                    print "***********************************\n"

            yield elec_name, contests, registered_voters, ballots_cast

    def make_elections_json(self, elec_name, contests, registered_voters, ballots_cast):
        # slug = re.sub(r'[^0-9a-z]+', '_', elec_name.lower().strip())
        elec_name = elec_name[5:]
        parts = elec_name.split(' - ')

        if 'special' in parts[0].lower():
            is_special = True
            if len(parts) == 3:
                name, seat, date = parts
                name_party = None
            elif len(parts) == 4:
                name, seat, name_party, date = parts
        else:
            is_special = False
            if len(parts) == 2:
                name, date = parts
                name_party = None
            elif len(parts) == 3:
                name, name_party, date = parts

        date_obj = parse(date)
        date_formatted = str(date_obj.year) + ('0'+str(date_obj.month))[-2:] + ('0'+str(date_obj.day))[-2:]

        # slug_parts = [date_formatted, 'il', re.sub(r'[^0-9a-z]+', '_', name.lower().strip()), 'precinct']
        slug_parts = [date_formatted, 'il']
        if name_party:
            slug_parts.append(name_party)
        if is_special:
            slug_parts.append('special')
        slug_parts.append(re.sub(r'[^0-9a-z]+', '_', name.lower().strip()))
        slug_parts.append('precinct')

        slug = '__'.join(slug_parts)

        filename = 'election_json/'+slug+'.json'

        if not os.path.exists(filename):

            election_json = {
                'election_name': elec_name,
                'date': None,
                'contests': [self.make_contest_json(contest_name, contest_urls) for contest_name, contest_urls in contests]
            }

            with open(filename, 'w+') as outfile:
                json.dump(election_json, outfile, indent=4)



    def make_summary_json(self, summary_urls):
        return {}

    def make_contest_json(self, contest_name, contest_urls):

        print '  CONTEST', contest_name

        contest_json = {
            'position': contest_name,
            'results': []
        }
        for ward, url in contest_urls:

            try:
                _, result = self.urlretrieve(url)
            except:
                print "******** urlretrieve failed for %s, usingg requests instead" %url
                print "_ %s" % _
                print "*"*60
                result = requests.get(url)

            tree = lxml.html.fromstring(result.text)

            header_td_list = tree.xpath("//table[1]//tr[2]//td")
            tbl_header = [td.xpath("string(.)") for td in header_td_list]
            num_cols = len(tbl_header)

            # finding the position of the last row of results (the row w/ totals)
            # b/c sometimes there are extra non-result rows in the table
            rows = tree.xpath("//table[1]//tr")
            first_col_str = [tr.xpath("td")[0].xpath("string(.)") if tr.xpath("td") else None for tr in rows]
            if 'Total' in first_col_str:
                idx_total_row = list(reversed(first_col_str)).index('Total')
                total_td_list = tree.xpath("//table[1]//tr[last()-%s]//td" % idx_total_row)
                totals = [td.xpath("string(.)") for td in total_td_list]
                precinct_td_list = tree.xpath("//table[1]//tr[position() > 2 and not(position() > last()-%s)]//td" % (idx_total_row+1))
                precinct_data = [precinct_td_list[i:i+num_cols] for i in range(0, len(precinct_td_list), num_cols)]
            else:
                precinct_td_list = tree.xpath("//table[1]//tr[position() > 2 and not(position() > last()-%s)]//td" % (idx_total_row+1))
                precinct_data = [precinct_td_list[i:i+num_cols] for i in range(0, len(precinct_td_list), num_cols)]
                totals = []
                for i in range(0, len(precinct_data[0])):
                    col_total = 0
                    for row in precinct_data:
                        try:
                            parsed_num = int(row[i].xpath("string(.)"))
                        except:
                            # sometimes these will be percentages but these will be ignored later anyways
                            parsed_num = 0
                        col_total += parsed_num
                    totals.append(col_total)
                print "TOTALS"
                print totals


            # TO-DO: distinguish between voting on candidates vs voting on Y/N vote?
            if len(tbl_header) > 2: # more than one candidate running
                candidates = tbl_header[2::2]
                votes_totals = totals[2::2]
            else: # only one candidate
                candidates = [tbl_header[1]]
                votes_totals = [totals[1]]

            results_by_precinct = []
            for row in precinct_data:
                row_string = [td.xpath("string(.)") for td in row]
                precinct = row_string[0]
                
                precinct_result = {
                    'precinct': precinct,
                    'candidate_totals': {}
                }
                if num_cols > 2:
                    votes_precinct = row_string[2::2]
                else: # only one candidate
                    votes_precinct = [row_string[1]]

                for candidate, vote in zip(candidates, votes_precinct):
                    precinct_result['candidate_totals'][candidate] = int(vote)

                results_by_precinct.append(precinct_result)

            candidate_totals = {}
            for candidate, votes_total in zip(candidates, votes_totals):
                candidate_totals[candidate] = int(votes_total)

            ward_result = {
                'ward': ward,
                'candidate_totals': candidate_totals,
                'results_by_precinct': results_by_precinct
            }

            contest_json['results'].append(ward_result)

        return contest_json 
        