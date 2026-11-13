from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Reward
from ..security import get_current_teacher, get_db, require_admin

router = APIRouter(prefix="/api/rewards", tags=["rewards"])


class RewardIn(BaseModel):
    name: str
    cost_coins: int = Field(gt=0)
    stock: int | None = Field(None, ge=0)


class RewardPatch(BaseModel):
    name: str | None = None
    cost_coins: int | None = Field(None, gt=0)
    stock: int | None = Field(None, ge=0)
    is_active: bool | None = None


def serialize_reward(r: Reward) -> dict:
    return {"id": r.id, "name": r.name, "cost_coins": r.cost_coins, "stock": r.stock, "is_active": r.is_active}


@router.get("")
def list_rewards(teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    rewards = db.scalars(select(Reward).where(Reward.is_active.is_(True)).order_by(Reward.cost_coins)).all()
    return {"items": [serialize_reward(r) for r in rewards]}


@router.post("")
def create_reward(body: RewardIn, admin=Depends(require_admin), db: Session = Depends(get_db)):
    reward = Reward(name=body.name, cost_coins=body.cost_coins, stock=body.stock)
    db.add(reward)
    db.commit()
    return serialize_reward(reward)


@router.patch("/{reward_id}")
def update_reward(reward_id: int, body: RewardPatch, admin=Depends(require_admin), db: Session = Depends(get_db)):
    reward = db.get(Reward, reward_id)
    if reward is None:
        raise HTTPException(status_code=404, detail="奖励不存在")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(reward, field, value)
    db.commit()
    return serialize_reward(reward)


@router.delete("/{reward_id}")
def delete_reward(reward_id: int, admin=Depends(require_admin), db: Session = Depends(get_db)):
    reward = db.get(Reward, reward_id)
    if reward is None:
        raise HTTPException(status_code=404, detail="奖励不存在")
    reward.is_active = False
    db.commit()
    return {"ok": True}