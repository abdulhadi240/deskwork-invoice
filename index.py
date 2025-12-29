from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime, date
from decimal import Decimal
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Invoice Statement Generator API",
    description="Production-ready API for generating invoice statements and payment advice",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Models
class InvoiceItem(BaseModel):
    date: date
    activity: str  # URL for the invoice link
    reference: str  # Display text for the link (anchor tag)
    due_date: str
    invoice_amount: Decimal = Field(ge=0)
    payments: Decimal = Field(default=Decimal("0.00"), ge=0)  # Kept in model but not displayed
    
    @validator('invoice_amount', 'payments')
    def round_decimal(cls, v):
        return round(v, 2)
    
    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            date: lambda v: v.isoformat()
        }

class StatementRequest(BaseModel):
    client_name: str = Field(..., min_length=1, max_length=200)
    company_name: str = Field(..., min_length=1, max_length=200)
    from_date: str
    to_date: str
    invoices: List[InvoiceItem] = Field(..., min_items=1)
    
    @validator('to_date')
    def validate_dates(cls, v, values):
        if 'from_date' in values and v < values['from_date']:
            raise ValueError('to_date must be after from_date')
        return v
    
    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            date: lambda v: v.isoformat()
        }

class StatementResponse(BaseModel):
    message: str
    total_due: float
    overdue_amount: float
    current_amount: float
    file_size: int

# PDF Generation Functions
def generate_statement_pdf(data: StatementRequest) -> bytes:
    """Generate PDF statement document with exact design"""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4  # 595 x 842 points
    
    # Define colors
    gray_line = colors.HexColor("#CCCCCC")
    blue_link = colors.HexColor("#0066CC")
    
    # Define margins
    left_margin = 40
    right_margin = 40
    available_width = width - left_margin - right_margin  # 515 points
    
    # Starting Y position
    y = height - 50
    
    # ============ HEADER SECTION ============
    # Title "STATEMENT - Activity"
    c.setFont("Helvetica", 22)
    c.drawString(left_margin, y, "OVERDUE STATEMENT")
    
    # Right side header info
    c.setFont("Helvetica-Bold", 9)
    c.drawString(360, y, "From Date")
    c.setFont("Helvetica", 9)
    c.drawString(480, y, data.client_name)
    
    y -= 15
    c.setFont("Helvetica", 9)
    c.drawString(360, y, data.from_date.strftime("%d %b %Y"))
    
    y -= 13
    c.setFont("Helvetica-Bold", 9)
    c.drawString(360, y, "To Date")
    
    y -= 15
    c.setFont("Helvetica", 9)
    c.drawString(360, y, data.to_date.strftime("%d %b %Y"))
    
    # Company name below title
    y = height - 105
    c.setFont("Helvetica", 10)
    c.drawString(left_margin, y, data.company_name)
    
    # ============ TABLE SECTION ============
    y = height - 165
    
    # Table column positions (without Reference and Payments columns)
    col_date = left_margin
    col_activity = left_margin + 75
    col_due_date = left_margin + 270
    col_invoice_amt = left_margin + 360
    col_balance = left_margin + 465
    
    # Draw table headers
    c.setFont("Helvetica-Bold", 9)
    c.drawString(col_date, y, "Date")
    c.drawString(col_activity, y, "Activity")
    c.drawString(col_due_date, y, "Due Date")
    c.drawRightString(col_invoice_amt + 50, y, "Invoice Amount")
    c.drawRightString(col_balance + 50, y, "Balance AUD")
    
    # Line under headers
    y -= 3
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(left_margin, y, width - right_margin, y)
    
    # Calculate running balance
    running_balance = Decimal("0.00")
    
    
    # ============ INVOICE ROWS ============
    for invoice in data.invoices:
        y -= 15
        balance = invoice.invoice_amount - invoice.payments
        running_balance += balance
        
        c.setFillColor(colors.black)
        
        # Date
        c.drawString(col_date, y, invoice.date.strftime("%d %b %Y"))
        
        # Activity - Display reference as clickable blue link
        c.setFillColor(blue_link)
        c.drawString(col_activity, y, invoice.reference)
        
        # Create clickable link area
        link_width = c.stringWidth(invoice.reference, "Helvetica", 9)
        c.linkURL(
            invoice.activity, 
            (col_activity, y - 2, col_activity + link_width, y + 10),
            relative=0
        )
        
        c.setFillColor(colors.black)
        
        # Due Date (single line: "14 Dec 2025")
        c.drawString(col_due_date, y, invoice.due_date.strftime("%d %b %Y"))
        
        # Invoice Amount
        c.drawRightString(col_invoice_amt + 50, y, f"{invoice.invoice_amount:,.2f}")
        
        # Balance
        c.drawRightString(col_balance + 50, y, f"{running_balance:,.2f}")
        
        # Light gray line
        y -= 3
        c.setStrokeColor(gray_line)
        c.line(left_margin, y, width - right_margin, y)
    
    # Bottom line
    y -= 10
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(left_margin, y, width - right_margin, y)
    
    # ============ BALANCE DUE ============
    y -= 25
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.black)
    balance_text = f"BALANCE DUE AUD  {running_balance:,.2f}"
    c.drawRightString(width - right_margin, y, balance_text)
    
    # ============ FULL WIDTH DOTTED LINE ============
    y -= 100
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.5)
    c.setDash([2, 2])  # Dotted line pattern
    c.line(left_margin, y, width - right_margin, y)
    c.setDash([])  # Reset to solid line
    
    # ============ PAYMENT ADVICE SECTION ============
    y -= 30
    c.setFont("Helvetica", 23)
    c.drawString(left_margin, y, "PAYMENT ADVICE")
    
    y -= 20
    c.setFont("Helvetica", 9)
    c.drawString(left_margin, y, f"To: {data.client_name}")
    
    # Calculate overdue and current
    today = date.today()
    overdue = sum(
        (inv.invoice_amount - inv.payments) 
        for inv in data.invoices 
        if inv.due_date < today
    )
    current = sum(
        (inv.invoice_amount - inv.payments) 
        for inv in data.invoices 
        if inv.due_date >= today
    )
    
    # ============ PAYMENT DETAILS TABLE ============
    y -= 35
    
    # Customer row
    c.setFont("Helvetica-Bold", 9)
    c.drawString(320, y, "Customer")
    c.setFont("Helvetica", 9)
    c.drawString(440, y, data.company_name)
    
    y -= 5
    # Line after Customer
    c.line(320, y, width - right_margin, y)
    
    y -= 13
    
    # Overdue, Current, Total row (all on one line)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(320, y, "Overdue")
    c.drawString(395, y, "Current")
    c.drawString(470, y, "Total AUD Due")
    
    y -= 15
    c.setFont("Helvetica", 9)
    c.drawString(320, y, f"{overdue:,.2f}")
    c.drawString(395, y, f"{current:,.2f}")
    c.drawString(470, y, f"{running_balance:,.2f}")
    
    y -= 5
    # Line after amounts
    c.line(320, y, width - right_margin, y)
    
    y -= 13
    
    # Amount Enclosed
    c.setFont("Helvetica-Bold", 9)
    c.drawString(320, y, "Amount Enclosed")
    
    y -= 5
    # Line after Amount Enclosed
    c.line(320, y, width - right_margin, y)
    
    
    
    # Save PDF
    c.save()
    
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes

# API Endpoints
@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Invoice Statement Generator API",
        "version": "1.0.0"
    }

@app.post(
    "/generate-statement",
    response_model=StatementResponse,
    tags=["Statement Generation"],
    summary="Generate invoice statement PDF"
)
async def generate_statement(request: StatementRequest):
    """
    Generate a PDF invoice statement and payment advice.
    
    - **client_name**: Name of the client receiving the statement
    - **company_name**: Name of the company issuing the statement
    - **from_date**: Start date of the statement period
    - **to_date**: End date of the statement period
    - **invoices**: List of invoice items where:
        - **activity**: URL for the invoice link
        - **reference**: Display text for the link (e.g., "Invoice # INV-003")
        - **date**: Invoice date
        - **due_date**: Payment due date
        - **invoice_amount**: Invoice amount
        - **payments**: Payments made (optional, defaults to 0)
    
    Returns the PDF file with statement and payment advice.
    """
    try:
        logger.info(f"Generating statement for {request.company_name}")
        
        # Calculate totals
        today = date.today()
        overdue = float(sum(
            (inv.invoice_amount - inv.payments) 
            for inv in request.invoices 
            if inv.due_date < today
        ))
        current = float(sum(
            (inv.invoice_amount - inv.payments) 
            for inv in request.invoices 
            if inv.due_date >= today
        ))
        total_due = overdue + current
        
        # Generate PDF
        pdf_bytes = generate_statement_pdf(request)
        
        logger.info(f"Statement generated successfully. Size: {len(pdf_bytes)} bytes")
        
        # Return PDF as response
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=statement_{request.company_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
            }
        )
        
    except Exception as e:
        logger.error(f"Error generating statement: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating statement: {str(e)}")

@app.post(
    "/preview-statement",
    response_model=StatementResponse,
    tags=["Statement Generation"],
    summary="Preview statement details without generating PDF"
)
async def preview_statement(request: StatementRequest):
    """
    Preview statement calculations without generating the PDF.
    Returns totals and summary information.
    """
    try:
        today = date.today()
        overdue = float(sum(
            (inv.invoice_amount - inv.payments) 
            for inv in request.invoices 
            if inv.due_date < today
        ))
        current = float(sum(
            (inv.invoice_amount - inv.payments) 
            for inv in request.invoices 
            if inv.due_date >= today
        ))
        total_due = overdue + current
        
        return StatementResponse(
            message="Statement preview generated successfully",
            total_due=round(total_due, 2),
            overdue_amount=round(overdue, 2),
            current_amount=round(current, 2),
            file_size=0
        )
    except Exception as e:
        logger.error(f"Error previewing statement: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# Error handlers
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return HTTPException(status_code=400, detail=str(exc))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)