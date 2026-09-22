"""Minimal reproductions of the supplied, UNEXECUTED PINN report's tensor bugs.
No PINN training, physics simulation or visualization is performed by these tests.
"""
import pytest

def test_boundary_concatenation_mixes_tensor_ranks():
    torch=pytest.importorskip('torch')
    X0,X1=-8.,20.
    s=torch.rand(1)
    xb=[torch.tensor([[X0]]), X0+(X1-X0)*s]
    with pytest.raises(RuntimeError,match='same number of dimensions'):
        torch.cat(xb)

def test_initial_condition_mask_uses_boundary_count():
    torch=pytest.importorskip('torch')
    mask=torch.zeros(4000,3)
    u=torch.ones(6000,1)
    with pytest.raises(RuntimeError,match='must match'):
        torch.where(mask>0.5,torch.ones_like(u),u*0)

def test_zero_initial_mask_enforces_no_initial_velocity():
    torch=pytest.importorskip('torch')
    mask=torch.zeros(6,3)
    u=v=torch.full((6,1),42.)  # Deliberately violates u=1 and v=0.
    inlet,wall_v,cyl=mask[:,0:1],mask[:,1:2],mask[:,2:3]
    eu=inlet*(u-1.)**2 + cyl*u**2
    ev=(wall_v+cyl)*v**2 + inlet*v**2
    assert (eu.mean()+ev.mean()).item()==0.0
