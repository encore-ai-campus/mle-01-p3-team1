import json
from argparse import Namespace

from src.agent.supervisor.llm import _context
from src.evaluation.hybrid.ragas_eval import ragas_context, _evidence_for_prompt, _fingerprint


def test_answer_verifier_and_judge_receive_identical_grounded_fields():
    row = {'museum_id': 'M1', 'evidence_id': 'E1', 'name': 'Museum',
           'text': 'Exhibition', 'score': 999, 'metadata': {'address': 'UNTRUSTED'},
           'metadata_provenance': {'source_kind': 'derived_csv_row',
               'source_locator': 'data/processed/example.csv#record=1',
               'trust': 'derived_dataset_not_human_verified',
               'fields': {'address': 'Verified row address', 'adult_fee': 0,
                          'weekday_open': '09:00', 'sido': 'Region'}}}
    answer = _context({'question': 'Where?', 'evidence': [row]})['evidence'][0]
    judge = ragas_context(row)
    assert answer == judge == _evidence_for_prompt([row])[0]
    data = json.loads(judge)
    assert data['museum_id'] == 'M1'
    assert data['metadata_provenance']['fields']['adult_fee'] == 0
    assert 'UNTRUSTED' not in judge and '999' not in judge
    assert row['metadata']['address'] == 'UNTRUSTED'


def test_unlinked_attributes_are_not_promoted_to_evidence():
    row = {'museum_id': 'M2', 'name': 'Museum', 'document': 'Full text' * 400,
           'metadata_provenance': {'fields': {'address': 'UNLINKED'}},
           'metadata': {'structured_match': {'amenity': 'UNLINKED'}}}
    value = ragas_context(row)
    assert 'UNLINKED' not in value
    assert json.loads(value)['text'] == row['document']


def test_format_version_is_part_of_resume_fingerprint(tmp_path):
    path = tmp_path / 'data.csv'
    path.write_text('data')
    fp = _fingerprint(path, [], Namespace(modes=['supervisor_full'], top_k=5), 'a', 's', 'g', 'j')
    assert fp['evidence_context_version'] == 'grounded-evidence-v2'


def test_old_checkpoint_cannot_resume_under_new_context(tmp_path):
    import pytest
    from src.evaluation.hybrid.ragas_eval import _open_run
    (tmp_path / 'checkpoint.json').write_text(json.dumps({'run_id': 'old', 'fingerprint': {}}))
    with pytest.raises(ValueError, match='evidence context version'):
        _open_run(Namespace(output=tmp_path, resume=str(tmp_path)),
                  {'evidence_context_version': 'grounded-evidence-v2'})


def test_raw_candidates_do_not_leak_through_diagnostics():
    context = _context({'question': 'Where?', 'evidence': [],
                        'hybrid_search_diagnostics': {'raw_candidates': ['SECRET_RAW_FACT']}})
    assert 'SECRET_RAW_FACT' not in json.dumps(context)
