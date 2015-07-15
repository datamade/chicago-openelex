import scrapelib
import lxml.html

class Scraper(scrapelib.Scraper):
    def __init__(   self,
                    raise_errors=True,
                    requests_per_minute=30,
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
        urls = []

        print '\n\ngrabbing election result urls\n\n'
        r = self.get(start_url)
        tree = lxml.html.fromstring(r.text)

        elec_options = tree.xpath("//table[@class='maincontent']//select/option/@value")
        for elec_name in elec_options[:3]: # limit for now
            print '* election name', elec_name
            post_data = {
                'D3' : elec_name,
                'flag1' : '1',
                'B1' : 'View'
                }
            
            try:
                _, result = self.urlretrieve(start_url, method='POST', body=post_data)
                tree = lxml.html.fromstring(result.text)
                contest_options = tree.xpath("//table[@class='maincontent']//select/option/@value")
                for contest_name in contest_options[:3]: # limit for now
                    print ' * contest name', contest_name
                    post_data = {
                        'D3' : contest_name,
                        'flag' : '1',
                        'B1' : '  View The Results   '
                        }

                    _, result = self.urlretrieve(result.url, method='POST', body=post_data)

                

               
            except Exception, e:
                print 'error', e

        return urls

if __name__ == '__main__':
    s = Scraper()
    
    s.election_urls()
