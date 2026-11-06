"""Regions and districts."""

from app.extensions import db


class Region(db.Model):
    __tablename__ = "regions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)

    # passive_deletes="all" leaves the decision to the database, which blocks
    # deleting a region that still has districts.
    districts = db.relationship("District", back_populates="region", passive_deletes="all")

    def __repr__(self):
        return f"<Region {self.name}>"


class District(db.Model):
    __tablename__ = "districts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    region_id = db.Column(
        db.Integer, db.ForeignKey("regions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sub_region = db.Column(db.String(80))

    region = db.relationship("Region", back_populates="districts")
    offices = db.relationship(
        "GovernmentOffice", back_populates="district", passive_deletes="all"
    )

    def __repr__(self):
        return f"<District {self.name}>"
