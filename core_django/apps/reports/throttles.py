from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

class ReportAnonRateThrottle(AnonRateThrottle):
    rate = '5/min'
    scope = 'report_anon'

class ReportUserRateThrottle(UserRateThrottle):
    rate = '20/min'
    scope = 'report_user'
