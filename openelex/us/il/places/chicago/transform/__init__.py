from datetime import datetime
import re

from openelex.base.transform import Transform, registry
from openelex.models import Candidate, Contest, Office, Party, RawResult, Result

STATE = 'IL'
PLACE = 'Chicago'


meta_fields = ['source', 'election_id', 'state', 'place']

contest_fields = meta_fields + ['start_date',
                                'end_date',
                                'election_type',
                                'primary_type',
                                'result_type',
                                'special',
                                ]
candidate_fields = meta_fields + ['full_name', 'given_name',
                                  'family_name', 'additional_name']
result_fields = meta_fields + ['reporting_level', 'jurisdiction',
                               'votes', 'total_votes', 'vote_breakdowns']


class BaseTransform(Transform):

    district_offices = set([
        'U.S. Senate',
        'U.S. House of Representatives',
        'State Senate',
        'State House of Representatives',
    ])

    def __init__(self):
        super(BaseTransform, self).__init__()

    def get_raw_results(self):
        return RawResult.objects.filter(state=STATE, place=PLACE).no_cache()

class CreateContestsTransform(BaseTransform):
    name = 'chicago_create_unique_contests'

    def __call__(self):
        contests = []
        seen = set()

        for result in self.get_raw_results():
            key = self._contest_key(result)
            if key not in seen:
                fields = self.get_contest_fields(result)
                if fields:
                    fields['updated'] = datetime.now()
                    fields['created'] = datetime.now()
                    contest = Contest(**fields)
                    contests.append(contest)
                    seen.add(key)

        print "SEEN:", seen
        Contest.objects.insert(contests, load_bulk=False)

    def _contest_key(self, raw_result):
        slug = raw_result.contest_slug
        return (raw_result.election_id, slug)

    def get_contest_fields(self, raw_result):
        fields = self._get_fields(raw_result, contest_fields)
        office = self._get_or_make_office(raw_result)
        if office:
            fields['office'] = office
            return fields
        else:
            return None

    def _get_fields(self, raw_result, field_names):
        return {k: getattr(raw_result, k) for k in field_names}

    def _get_or_make_office(self, raw_result):
        clean_name = self._clean_office_name(raw_result.office)

        if clean_name:

            office_query = self._make_office_query(clean_name, raw_result)

            try:
                office = Office.objects.get(**office_query)
                return office
            except Office.DoesNotExist:
                office = Office(**office_query)
                office.save()
                return office
        else:
            return None

    def _make_office_query(self, office_name, raw_result):
        """
        Gets the right state, place, district for an office
        """

        office_query = {
            'name': office_name
        }

        if office_name is 'President':
            office_query['state'] = 'US'
            office_query['place'] = None

        if office_name in self.district_offices:
            office_query['state'] = STATE
            if raw_result.district:
                office_query['district'] = raw_result.district

        return office_query


    def _clean_office_name(self, office):
        """
        See: https://github.com/openelections/core/blob/dev/openelex/us/wa/load.py#L370

        """

        us_pres_regex = re.compile('president.+united\sstates|pres\sand\svice\spres', re.IGNORECASE)
        if re.search(us_pres_regex, office):
            return 'President'

        us_senator_regex = re.compile('senator.+u\.s\.|u\.s\..+senator|united\sstates\ssenator', re.IGNORECASE)
        if re.search(us_senator_regex, office):
            return 'U.S. Senate'

        return None



registry.register('il', CreateContestsTransform)

