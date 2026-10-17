import os
import uuid
import qrcode
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas

import models
from database import engine, Base, get_db

# Initialize Database Tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="EventPass - College Fest Ticketing System", version="1.0")

# --- Pydantic Data Validation Schemas ---
class UserCreate(BaseModel):
    name: str
    email: str
    role: str = "student"

class EventCreate(BaseModel):
    title: str
    description: str
    date: str
    total_seats: int
    ticket_price: int = 0

class BookingCreate(BaseModel):
    user_id: int
    event_id: int

# --- API ROUTES ---

# Serve Frontend Web Portal
@app.get("/")
def serve_frontend():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"message": "Welcome to EventPass API Backend! Open /docs for API documentation."}

# 1. Register User
@app.post("/users/")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(models.User).filter(models.User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email is already registered!")
    
    db_user = models.User(name=user.name, email=user.email, role=user.role)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# 2. Add New Event
@app.post("/events/")
def create_event(event: EventCreate, db: Session = Depends(get_db)):
    db_event = models.Event(
        title=event.title,
        description=event.description,
        date=event.date,
        total_seats=event.total_seats,
        available_seats=event.total_seats,
        ticket_price=event.ticket_price
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event

# 3. Get All Events
@app.get("/events/")
def get_events(db: Session = Depends(get_db)):
    return db.query(models.Event).all()

# 4. Book Ticket / Pass
@app.post("/book/")
def book_ticket(booking: BookingCreate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == booking.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found!")

    event = db.query(models.Event).filter(models.Event.id == booking.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found!")

    if event.available_seats <= 0:
        raise HTTPException(status_code=400, detail="Event is sold out! No seats available.")

    pass_code = f"PASS-{uuid.uuid4().hex[:8].upper()}"
    event.available_seats -= 1

    db_booking = models.Booking(
        booking_id=pass_code,
        user_id=booking.user_id,
        event_id=booking.event_id
    )
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)

    return {
        "status": "Success",
        "message": "Ticket booked successfully!",
        "pass_code": pass_code,
        "event_name": event.title,
        "user_name": user.name
    }

# 5. Get All Bookings
@app.get("/bookings/")
def get_bookings(db: Session = Depends(get_db)):
    return db.query(models.Booking).all()

# 6. Venue Gate Scanner Verification Endpoint
@app.get("/verify/{booking_id}")
def verify_ticket(booking_id: str, db: Session = Depends(get_db)):
    booking = db.query(models.Booking).filter(models.Booking.booking_id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Invalid Ticket / Pass Code Not Found!")
    
    return {
        "status": "VALID",
        "pass_code": booking.booking_id,
        "attendee_name": booking.user.name,
        "event_title": booking.event.title,
        "event_date": booking.event.date,
        "booking_time": booking.booking_time.strftime("%Y-%m-%d %H:%M:%S")
    }

# 7. Generate & Download Styled PDF Ticket with QR Code
@app.get("/ticket/{booking_id}/pdf")
def generate_ticket_pdf(booking_id: str, db: Session = Depends(get_db)):
    booking = db.query(models.Booking).filter(models.Booking.booking_id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found!")

    # Generate QR Code Image
    qr_img = qrcode.make(booking.booking_id)
    qr_path = f"qr_{booking.booking_id}.png"
    qr_img.save(qr_path)

    # Setup Canvas
    pdf_filename = f"Ticket_{booking.booking_id}.pdf"
    c = canvas.Canvas(pdf_filename, pagesize=letter)

    card_x, card_y = 50, 450
    card_w, card_h = 512, 280

    # Drop Shadow
    c.setFillColor(colors.HexColor("#E2E8F0"))
    c.roundRect(card_x + 4, card_y - 4, card_w, card_h, 12, fill=1, stroke=0)

    # Main Card Container
    c.setFillColor(colors.HexColor("#FFFFFF"))
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(1.5)
    c.roundRect(card_x, card_y, card_w, card_h, 12, fill=1, stroke=1)

    # Top Header Banner
    c.setFillColor(colors.HexColor("#4F46E5"))  # Royal Indigo
    c.rect(card_x, card_y + card_h - 55, card_w, 55, fill=1, stroke=0)

    # Header Text
    c.setFillColor(colors.HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(card_x + 20, card_y + card_h - 35, "EVENTPASS  |  OFFICIAL ENTRY PASS")

    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(card_x + card_w - 20, card_y + card_h - 32, "ADMIT ONE")

    # Event Title
    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont("Helvetica-Bold", 15)
    c.drawString(card_x + 20, card_y + card_h - 85, booking.event.title)

    # Dynamic Field Helper
    def draw_field(y_pos, label, value):
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#64748B"))
        c.drawString(card_x + 20, y_pos, label.upper())
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(colors.HexColor("#1E293B"))
        c.drawString(card_x + 20, y_pos - 15, str(value))

    draw_field(card_y + card_h - 115, "Attendee Name", booking.user.name)
    draw_field(card_y + card_h - 160, "Pass ID", booking.booking_id)
    draw_field(card_y + card_h - 205, "Event Date", booking.event.date)

    # Dashed Stub Divider Line
    stub_x = card_x + card_w - 160
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(1)
    c.setDash(4, 4)
    c.line(stub_x, card_y + 15, stub_x, card_y + card_h - 70)
    c.setDash()

    # QR Code Section
    c.drawImage(qr_path, stub_x + 20, card_y + 80, width=120, height=120)

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawCentredString(stub_x + 80, card_y + 60, "SCAN AT ENTRY GATE")

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#10B981"))
    c.drawCentredString(stub_x + 80, card_y + 40, "• VALID TICKET")

    # Footer Branding
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#94A3B8"))
    c.drawString(card_x + 20, card_y + 18, "Powered by EventPass System • Please present valid college ID at entrance")

    c.save()

    if os.path.exists(qr_path):
        os.remove(qr_path)

    return FileResponse(pdf_filename, media_type="application/pdf", filename=pdf_filename)
    