import pytest
from .animal_splits import draw_roles,create_split
from .test_shared import checkpoint_with_maps
from .shared_storage import read


def test_uniform_draw_is_stable_to_order_and_keeps_ineligible_diagnostic():
    ids=list(map(str,range(1,44)))
    roles=draw_roles(ids,ids+['54'],9,20261104)
    assert roles==draw_roles(list(reversed(ids)),['54']+ids,9,20261104)
    assert sum(v=='train'for v in roles.values())==34
    assert sum(v=='test'for v in roles.values())==9
    assert roles['54']=='unassigned'
    with pytest.raises(ValueError):draw_roles(ids,ids,43,1)


def test_split_is_frozen_and_export_complete(tmp_path):
    checkpoint,groups,_,_,export=checkpoint_with_maps(tmp_path)
    out=tmp_path/'allocation'
    path=create_split(checkpoint,export,'WIN-C01',out,1,42)
    roles=read(path);assert len(roles)==2 and set(roles.values())=={'train','test'}
    assert read(out/'split_metadata.json')['group_constraints'] is False
    assert create_split(checkpoint,export,'WIN-C01',out,1,42)==path
    with pytest.raises(ValueError,match='Frozen split differs'):
        create_split(checkpoint,export,'WIN-C01',out,1,43)
