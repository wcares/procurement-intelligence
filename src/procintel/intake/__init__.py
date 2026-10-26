"""Intake: documents people add by upload (docs/event-pipeline-design.md section 6b).

A file is stored and fingerprinted (store), its text read by format (extract), what it is decided (classify), and the
projects and countries it names found (link). A completion report linked to a known project is added to the evidence
corpus and reported as an Upload.ingested event, which the rules turn into cutting and indexing its passages like any
other new report (process). Other kinds are kept, classified and linked, and listed for review.
"""
