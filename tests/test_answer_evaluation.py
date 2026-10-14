import importlib.util
from pathlib import Path

from pypdf import PdfReader
from io import BytesIO

spec=importlib.util.spec_from_file_location('answer_eval',Path(__file__).resolve().parents[1]/'scripts/evaluate_answers.py')
evaluation=importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def test_fixture_has_selectable_physical_pages():
    data=evaluation.pdf_bytes({'title':'Synthetic test','pages':[{'heading':'One','text':'Fact number one.'},{'heading':'Two','text':'Fact number two.'}]})
    reader=PdfReader(BytesIO(data))
    assert len(reader.pages)==2
    assert 'Fact number two.' in reader.pages[1].extract_text()


def test_answers_require_word_boundaries_and_complete_response():
    case={'answerable':True,'expected_terms':['12'],'expected_page':1}
    assert evaluation.score(case,'120 credits',[],True)['answer_match'] is False
    assert evaluation.score(case,'12 credits',[],False)['answer_match'] is False
    assert evaluation.score(case,'12 credits',[],True)['answer_match'] is True


def test_citation_requires_matching_page_support_and_source():
    case={'answerable':True,'expected_terms':['five'],'expected_page':2}
    source={'chunk_index':3,'page':2,'text':'Refunds take five business days.'}
    result=evaluation.score(case,'5 business days 【Chunk\u00a03】',[source],True)
    assert result['citation_hit'] is True
    source['page']=1
    assert evaluation.score(case,'five days [Chunk 3]',[source],True)['citation_hit'] is False
    assert evaluation.score(case,'five days [Chunk 99]',[source],True)['citation_hit'] is False


def test_abstention_is_only_a_heuristic_not_a_citation_success():
    case={'answerable':False,'expected_terms':[],'expected_page':None}
    result=evaluation.score(case,'I could not find the answer in the document.',[],True)
    assert result['answer_match'] is True
    assert result['citation_hit'] is None
