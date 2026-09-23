from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_athlete, get_db
from app.models.athlete import Athlete
from app.models.coach import CoachAthleteAssignment, CoachAthleteInvitation
from app.schemas.coach import CoachConnectionRead, CoachInvitationRead

router = APIRouter(prefix="/athlete/coaches", tags=["athlete coach connections"])


def _invitation_read(invitation: CoachAthleteInvitation) -> CoachInvitationRead:
    return CoachInvitationRead(
        id=invitation.id,
        coach_id=invitation.coach_id,
        coach_name=invitation.coach.display_name or invitation.coach.email,
        athlete_id=invitation.athlete_id,
        athlete_name=invitation.athlete.name,
        athlete_email=invitation.athlete.user.email,
        created_at=invitation.created_at,
    )


@router.get("/invitations", response_model=list[CoachInvitationRead])
def list_received_invitations(
    athlete: Athlete = Depends(get_current_athlete),
    db: Session = Depends(get_db),
) -> list[CoachInvitationRead]:
    invitations = db.query(CoachAthleteInvitation).filter(
        CoachAthleteInvitation.athlete_id == athlete.id
    ).order_by(CoachAthleteInvitation.created_at.desc()).all()
    return [_invitation_read(invitation) for invitation in invitations]


def _owned_invitation(invitation_id: int, athlete: Athlete, db: Session) -> CoachAthleteInvitation:
    invitation = db.query(CoachAthleteInvitation).filter_by(
        id=invitation_id, athlete_id=athlete.id
    ).first()
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    return invitation


@router.post("/invitations/{invitation_id}/accept", response_model=CoachConnectionRead)
def accept_invitation(
    invitation_id: int,
    athlete: Athlete = Depends(get_current_athlete),
    db: Session = Depends(get_db),
) -> CoachConnectionRead:
    invitation = _owned_invitation(invitation_id, athlete, db)
    assignment = db.query(CoachAthleteAssignment).filter_by(
        coach_id=invitation.coach_id, athlete_id=athlete.id
    ).first()
    if assignment is None:
        assignment = CoachAthleteAssignment(coach_id=invitation.coach_id, athlete_id=athlete.id)
        db.add(assignment)
    coach = invitation.coach
    db.delete(invitation)
    db.commit()
    db.refresh(assignment)
    return CoachConnectionRead(
        coach_id=coach.id,
        coach_name=coach.display_name or coach.email,
        coach_email=coach.email,
        assigned_at=assignment.created_at,
    )


@router.post("/invitations/{invitation_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_invitation(
    invitation_id: int,
    athlete: Athlete = Depends(get_current_athlete),
    db: Session = Depends(get_db),
) -> None:
    invitation = _owned_invitation(invitation_id, athlete, db)
    db.delete(invitation)
    db.commit()


@router.get("", response_model=list[CoachConnectionRead])
def list_connected_coaches(
    athlete: Athlete = Depends(get_current_athlete),
    db: Session = Depends(get_db),
) -> list[CoachConnectionRead]:
    assignments = db.query(CoachAthleteAssignment).filter(
        CoachAthleteAssignment.athlete_id == athlete.id
    ).order_by(CoachAthleteAssignment.created_at.desc()).all()
    return [
        CoachConnectionRead(
            coach_id=assignment.coach.id,
            coach_name=assignment.coach.display_name or assignment.coach.email,
            coach_email=assignment.coach.email,
            assigned_at=assignment.created_at,
        )
        for assignment in assignments
    ]


@router.delete("/{coach_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_coach(
    coach_id: int,
    athlete: Athlete = Depends(get_current_athlete),
    db: Session = Depends(get_db),
) -> None:
    assignment = db.query(CoachAthleteAssignment).filter_by(
        coach_id=coach_id, athlete_id=athlete.id
    ).first()
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coach connection not found")
    db.delete(assignment)
    db.commit()
