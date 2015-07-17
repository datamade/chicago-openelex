import scrapelib
import lxml.html
import os
import json
import re


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

        print '\n\ngrabbing election result urls\n\n'
        r = self.get(start_url)
        tree = lxml.html.fromstring(r.text)

        elec_options = tree.xpath("//table[@class='maincontent']//select/option/@value")
        for elec_name in elec_options[:2]: # limit for now
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
            for contest_name in contest_options[:10]:
                post_data = {
                    'D3' : contest_name,
                    'flag' : '1',
                    'B1' : '  View The Results   '
                    }

                _, result = self.urlretrieve(result.url, method='POST', body=post_data)
                contest_urls = []

                tree = lxml.html.fromstring(result.text)
                links = tree.xpath("//table//tr//td[1]//a")
                if 'REGISTERED VOTERS - TOTAL' in contest_name:
                    registered_voters = [(link.text, self.base_url+'en/'+link.attrib['href']) for link in links]
                elif 'BALLOTS CAST - TOTAL' in contest_name:
                    ballots_cast = [(link.text, self.base_url+'en/'+link.attrib['href']) for link in links]
                else:
                    print '  CONTEST', contest_name
                    for link in links:
                        contest_urls.append((link.text, self.base_url+'en/'+link.attrib['href']))
                    contests.append((contest_name, contest_urls))

            yield elec_name, contests, registered_voters, ballots_cast

    def make_elections_json(self, elec_name, contests, registered_voters, ballots_cast):
        slug = re.sub(r'[^0-9a-z]+', '_', elec_name.lower().strip())
        filename = 'election_json/'+slug+'.json'

        if not os.path.exists(filename):

            election_json = {
                'election_name': elec_name,
                'date': None,
                'registered_voters': self.make_summary_json(registered_voters),
                'ballots_cast': self.make_summary_json(ballots_cast),
                'contests': [self.make_contest_json(contest_name, contest_urls) for contest_name, contest_urls in contests]
            }

            with open(filename, 'w+') as outfile:
                json.dump(election_json, outfile)



    def make_summary_json(self, summary_urls):
        return {}

    def make_contest_json(self, contest_name, contest_urls):

        contest_json = {
            'position': contest_name,
            'results': []
        }
        for ward, url in contest_urls:

            _, result = self.urlretrieve(url)
            tree = lxml.html.fromstring(result.text)

            header_td_list = tree.xpath("//table//tr[2]//td")
            tbl_header = [td.xpath("string(.)") for td in header_td_list]
            num_cols = len(tbl_header)

            total_td_list = tree.xpath("//table//tr[last()-3]//td")
            totals = [td.xpath("string(.)") for td in total_td_list]

            precinct_td_list = tree.xpath("//table//tr[position() > 2 and not(position() > last()-4)]//td")
            precinct_data = [precinct_td_list[i:i+num_cols] for i in range(0, len(precinct_td_list), num_cols)]



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
                    precinct_result['candidate_totals'][candidate] = vote

                results_by_precinct.append(precinct_result)

            candidate_totals = {}
            for candidate, votes_total in zip(candidates, votes_totals):
                candidate_totals[candidate] = votes_total

            ward_result = {
                'ward': ward,
                'candidate_totals': candidate_totals,
                'results_by_precinct': results_by_precinct
            }

            contest_json['results'].append(ward_result)

        return contest_json

if __name__ == '__main__':
    if not os.path.exists('election_json'):
        os.mkdir('election_json')

    s = Scraper()
    
    for elec_name, contests, registered_voters, ballots_cast in s.election_urls():
        s.make_elections_json(elec_name, contests, registered_voters, ballots_cast)
