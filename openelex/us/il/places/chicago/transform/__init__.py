from datetime import datetime
import re
import probablepeople as pp

from openelex.base.transform import Transform, registry
from openelex.models import Candidate, Contest, Office, Party, RawResult, Result

STATE = 'IL'
PLACE = 'Chicago'
COUNTY = 'Cook'


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

    # these are offices where we have to parse district
    # out of the office name
    district_offices = set([
        'U.S. Senator',
        'U.S. Representative',
        'State Senator',
        'State Representative',
        'County Commissioner'
    ])

    def __init__(self):
        super(BaseTransform, self).__init__()
        self._contest_cache = {}

    def get_raw_results(self):
        return RawResult.objects.filter(state=STATE, place=PLACE).no_cache()

    def get_judge_candidate_fields(self, raw_result):
        fields = self._get_fields(raw_result, candidate_fields)
        fields['full_name'] = None
        return fields

    def get_candidate_fields(self, raw_result):
        fields = self._get_fields(raw_result, candidate_fields)
        full_name = raw_result.full_name.strip()

        if full_name.lower() not in ['no candidate', 'candidate withdrew']:
            fields['full_name'] = None
            return fields

        try:
            name_parts, name_type = pp.tag(full_name)

            if name_type != 'Person':
                print "***************************"
                print "NOT A PERSON:", fields['full_name']
                print "fields:", fields
                print "tagged name:", name_parts
                print "***************************"
                fields['full_name'] = full_name
                return fields

            fields['given_name'] = name_parts.get('GivenName')
            fields['family_name'] = name_parts.get('Surname')
            if 'SuffixGenerational' in name_parts:
                fields['suffix'] = name_parts['SuffixGenerational']
            if 'Nickname' in name_parts:
                fields['additional_name'] = name_parts['Nickname']

            fields['full_name'] = full_name

        except pp.RepeatedLabelError:
            print "***************************"
            print "UNABLE TO TAG:", full_name
            print "***************************"
            fields['full_name'] = full_name

        return fields

    def _get_fields(self, raw_result, field_names):
        return {k: getattr(raw_result, k) for k in field_names}

    def get_contest(self, raw_result):
        """
        Returns the Contest model instance for a given RawResult.

        Caches the result in memory to reduce the number of calls to the
        datastore.
        """
        key = "%s-%s" % (raw_result.election_id, raw_result.contest_slug)

        fields = self.get_contest_fields(raw_result)

        if fields and fields['office']:
            fields.pop('source')
            try:
                try:
                    contest = Contest.objects.filter(**fields)[0]
                except IndexError:
                    contest = Contest.objects.get(**fields)
            except Exception:
                print fields
                print "\n"
                raise
            return contest
        else:
            return None

    def get_contest_fields(self, raw_result):
        fields = self._get_fields(raw_result, contest_fields)
        office = self._get_or_make_office(raw_result)
        if office:
            fields['office'] = office
            return fields
        else:
            return None

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

    def _clean_office_name(self, office):
        """
        See: https://github.com/openelections/core/blob/dev/openelex/us/wa/load.py#L370

        """

        us_pres =       ('president.+united\sstates|pres\sand\svice\spres', 
                        'President')
        us_senator =    ('senator.+u\.s\.|u\.s\..+senator|united\sstates\ssenator',
                        'U.S. Senator')
        us_rep =        ('u\.s\.\srepresentative|rep.+in\scongress',
                        'U.S. Representative')

        state_senator = ('state\ssenator',
                        'State Senator')
        state_rep =     ('state\srepresentative|rep.+gen.+assembly',
                        'State Representative')
        gov_lt_gov =    ('governor.+lieutenant\sgovernor',
                        'Governor & Lieutenant Governor')
        lt_gov =        ('lieutenant\sgovernor',
                        'Lieutenant Governor')
        gov =           ('governor',
                        'Governor')
        sec_state =     ('secretary',
                        'Secretary of State')
        aty_gen =       ('attorney\sgeneral',
                        'Attorney General')
        state_aty =     ('state.+attorney',
                        'State\'s Attorney')
        comptroller =   ('comptroller',
                        'Comptroller')
        county_treas =  ('county.+treasurer|treasurer.+county',
                        'County Treasurer') # should 'County' be in the office name?
        state_treas =   ('treasurer',
                        'Treasurer')

        # should 'County' be in the office name?
        county_board_pres = ('board.+pres.+county|county.+board.+pres|pres.+county.+board',
                        'County Board President')
        county_board_comm = ('county.+comm|comm.+county',
                        'County Commissioner')
        sheriff =       ('sheriff',
                        'County Sheriff')
        assessor =      ('assessor',
                        'County Assessor')
        rec_deeds =     ('deeds',
                        'County Recorder of Deeds')
        cir_ct_clerk =  ('circuit.+clerk|clerk.+circuit',
                        'County Circuit Court Clerk')
        clerk =         ('clerk',
                        'County Clerk')

        supreme_ct =    ('supreme\scourt',
                        'Supreme Court Judge')
        appellate_ct =  ('app?ellate\scourt',
                        'Appellate Court Judge')
        subcircuit_ct = ('judge.+circuit.+\d|judge.+\d.+sub|circuit.+court.+\d.+sub|judge.+subcircuit',
                        'Circuit Court Judge')
        circuit_ct_full = ('circuit.+judge|judge.+circuit',
                        'Circuit Court Judge')

        mayor =         ('mayor',
                        'Mayor')
        alderman =      ('alderman',
                        'Alderman')
        committeeman =  ('committeeman',
                        'Ward Committeeman')

        # the order of searches matters (b/c of overlapping keywords)
        office_searches = [us_pres, us_senator, us_rep, state_senator, state_rep,
                          gov_lt_gov, lt_gov, gov, sec_state, aty_gen, state_aty, comptroller,
                          county_treas, state_treas, county_board_pres, county_board_comm,
                          sheriff, assessor, rec_deeds, cir_ct_clerk, clerk,
                          supreme_ct, appellate_ct, subcircuit_ct, circuit_ct_full,
                          mayor, alderman, committeeman]

        for srch_regex, clean_office_name in office_searches:
            if re.search(srch_regex, office):
                return clean_office_name

        return None

    def _make_office_query(self, office_name, raw_result):
        """
        Gets the right state, place, district for an office
        """

        office_query = {
            'name': office_name,
            'state': STATE
        }
        office_name_raw = raw_result.office

        if office_name == 'President':
            office_query['state'] = 'US'

        if office_name in self.district_offices:
            if re.findall("\d+", office_name_raw):
                office_query['district'] = re.findall("\d+", office_name_raw)[0]
            else:
                office_query['district'] = None
        if office_name == 'Circuit Court Judge':
            if re.findall("\d+", office_name_raw):
                office_query['district'] = 'Subcircuit '+re.findall("\d+", office_name_raw)[0]
            else:
                office_query['district'] = None

        if office_name in ['Mayor', 'Alderman', 'Ward Committeeman']:
            office_query['place'] = PLACE

        if office_name in ['Alderman', 'Ward Committeeman']:
            if re.findall("\d+", office_name_raw):
                office_query['district'] = 'Ward '+re.findall("\d+", office_name_raw)[0]

        if re.search('county', office_name_raw) and 'judge' not in office_name.lower():
            office_query['county'] = COUNTY

        return office_query


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
                    print "   %s", contest
                    contests.append(contest)
                    seen.add(key)

        Contest.objects.insert(contests, load_bulk=False)

    def _contest_key(self, raw_result):
        slug = raw_result.contest_slug
        return (raw_result.election_id, slug)


class CreateCandidatesTransform(BaseTransform):
    name = 'chicago_create_unique_candidates'

    def __init__(self):
        super(CreateCandidatesTransform, self).__init__()

    def __call__(self):
        candidates = []
        seen = set()

        for rr in self.get_raw_results():
            key = (rr.election_id, rr.contest_slug, rr.candidate_slug)
            if key not in seen:

                if rr.full_name.lower().strip() in ['yes', 'no']:
                    fields = self.get_judge_candidate_fields(rr)
                else:
                    fields = self.get_candidate_fields(rr)

                if fields['full_name']:
                    contest = self.get_contest(rr)
                    if contest:
                        fields['contest'] = contest
                        candidate = Candidate(**fields)
                        print "*", candidate.full_name
                        candidates.append(candidate)

                seen.add(key)


        Candidate.objects.insert(candidates, load_bulk=False)

    def reverse(self):
        old = Candidate.objects.filter(state=STATE)
        print "\tDeleting %d previously created candidates" % old.count()
        old.delete()


registry.register('il', CreateContestsTransform)
registry.register('il', CreateCandidatesTransform)

