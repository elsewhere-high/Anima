import base64,io
import numpy as np
import pytest
from PIL import Image
from social_v5.vision import decode_image,iou,Vision

def encoded(size=(100,100)):
    f=io.BytesIO();Image.new('RGB',size).save(f,format='PNG');return base64.b64encode(f.getvalue()).decode()

def test_image_validation():
    assert decode_image(encoded()).shape==(100,100,3)
    with pytest.raises(ValueError):decode_image('bad image')
    with pytest.raises(ValueError):decode_image(encoded((5010,40)))
    with pytest.raises(ValueError):decode_image('data:image/svg+xml;base64,'+encoded())

def test_quality_rejects_tiny_dark_blurred():
    v=Vision.__new__(Vision)
    q,_=v.quality(np.zeros((100,100,3),np.uint8),np.array([10,10,30,30,15,20,30,20,22,27,18,34,29,34,.99]))
    assert not q['usable'] and {'face_too_small','poor_lighting','blurred'}<=set(q['reasons'])

def test_identity_unknown_and_ambiguity():
    class Memory:
        def faces(self):return [('a',{'embeddings':[[1,0],[1,0],[1,0]]}),('b',{'embeddings':[[.99,.01],[.99,.01],[.99,.01]]})]
    v=Vision.__new__(Vision);v.memory=Memory()
    assert v.match(np.array([1,0]))['status']=='unknown'
    assert v.match(np.array([0,1]))['status']=='unknown'
    assert not v.match(np.array([1,0]))['identity_verified']

def test_iou():
    assert iou([0,0,10,10],[0,0,10,10])==1
    assert iou([0,0,10,10],[20,20,10,10])==0
