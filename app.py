from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import statistics
import os
from functools import wraps

app = Flask(__name__, static_folder='public', template_folder='public')
app.secret_key = os.environ.get('SECRET_KEY', 'supersecretkey123')

# Database configuration - Works locally AND on PythonAnywhere
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    # Get the absolute path of the current directory
    basedir = os.path.abspath(os.path.dirname(__file__))
    
    # Try /tmp for serverless, otherwise use local directory
    if os.access('/tmp', os.W_OK):
        db_path = os.path.join('/tmp', 'school.db')
    else:
        # Use instance folder for better organization
        instance_folder = os.path.join(basedir, 'instance')
        os.makedirs(instance_folder, exist_ok=True)
        db_path = os.path.join(instance_folder, 'school.db')
    
    DATABASE_URL = f'sqlite:///{db_path}'

# Fix for PostgreSQL URL format if using external DB
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# School Information - Centralized Configuration
SCHOOL_INFO = {
    'name': 'SOW THE SEED Model College',
    'logo': 'logo1.png',
    'address': 'Olosan Road, Alakia',
    'phone1': '08033269042',
    'phone2': '08138044735',
    'motto': 'We all shall be taught of God - John 6:45'
}

# ============ DATABASE MODELS ============

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='teacher')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    admission_number = db.Column(db.String(50), unique=True)
    student_class = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    scores = db.relationship('Score', backref='student', lazy=True, cascade='all, delete-orphan')


class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    code = db.Column(db.String(10))
    scores = db.relationship('Score', backref='subject', lazy=True)


class Term(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    academic_year = db.Column(db.String(20), nullable=False)
    is_current = db.Column(db.Boolean, default=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)


class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('term.id'), nullable=False)
    ca1 = db.Column(db.Float, default=0)
    ca2 = db.Column(db.Float, default=0)
    exam = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)
    grade = db.Column(db.String(2))
    teacher_remark = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def calculate_total(self):
        self.total = self.ca1 + self.ca2 + self.exam
        self.grade = get_grade(self.total)


# ============ HELPER FUNCTIONS ============

def get_grade(score):
    """Calculate grade based on score"""
    if score >= 70: return "A"
    elif score >= 60: return "B"
    elif score >= 50: return "C"
    elif score >= 45: return "D"
    elif score >= 40: return "E"
    else: return "F"


def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def get_current_term():
    """Get the current active term"""
    return Term.query.filter_by(is_current=True).first()


def calculate_class_statistics(student_class, term_id):
    """Calculate class-wide statistics"""
    students = Student.query.filter_by(student_class=student_class).all()
    stats = {}
    
    for student in students:
        scores = Score.query.filter_by(student_id=student.id, term_id=term_id).all()
        total = sum(score.total for score in scores)
        stats[student.id] = {
            'name': student.name,
            'total': total,
            'average': total / len(scores) if scores else 0
        }
    
    sorted_students = sorted(stats.items(), key=lambda x: x[1]['total'], reverse=True)
    for position, (student_id, data) in enumerate(sorted_students, 1):
        stats[student_id]['position'] = position
    
    return stats


# Initialize database on first request
@app.before_request
def init_db():
    """Initialize database with sample data on first request"""
    if not hasattr(app, 'db_initialized'):
        with app.app_context():
            db.create_all()
            
            if not User.query.filter_by(username='admin').first():
                admin = User(username='admin', role='admin')
                admin.set_password('password123')
                db.session.add(admin)
            
            default_subjects = ['Mathematics', 'English', 'Science', 'Social Studies']
            for subject_name in default_subjects:
                if not Subject.query.filter_by(name=subject_name).first():
                    subject = Subject(name=subject_name, code=subject_name[:3].upper())
                    db.session.add(subject)
            
            if not Term.query.first():
                term = Term(
                    name='First Term',
                    academic_year='2024/2025',
                    is_current=True
                )
                db.session.add(term)
            
            db.session.commit()
            app.db_initialized = True


# Context processor to make SCHOOL_INFO available to all templates
@app.context_processor
def inject_school_info():
    return dict(school_info=SCHOOL_INFO)


# ============ ROUTES ============

@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
            return render_template('login.html', error='Invalid username or password')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    current_term = get_current_term()
    students = Student.query.order_by(Student.student_class, Student.name).all()
    classes = db.session.query(Student.student_class).distinct().all()
    classes = [c[0] for c in classes]
    
    return render_template('dashboard.html', 
                         students=students, 
                         classes=classes,
                         current_term=current_term)


@app.route('/student/add', methods=['GET', 'POST'])
@app.route('/add_student', methods=['GET', 'POST'])
@login_required
def add_student():
    if request.method == 'POST':
        name = request.form.get('name')
        admission_number = request.form.get('admission_number')
        student_class = request.form.get('student_class')
        
        existing = Student.query.filter_by(admission_number=admission_number).first()
        if existing:
            flash('Admission number already exists!', 'error')
            return redirect(url_for('add_student'))
        
        student = Student(
            name=name,
            admission_number=admission_number,
            student_class=student_class
        )
        
        db.session.add(student)
        db.session.commit()
        
        flash(f'Student {name} added successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('add_student.html')


@app.route('/student/<int:student_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_student(student_id):
    student = Student.query.get_or_404(student_id)
    
    if request.method == 'POST':
        student.name = request.form.get('name')
        student.admission_number = request.form.get('admission_number')
        student.student_class = request.form.get('student_class')
        
        db.session.commit()
        flash('Student updated successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('edit_student.html', student=student)


@app.route('/student/<int:student_id>/delete')
@login_required
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    name = student.name
    
    db.session.delete(student)
    db.session.commit()
    
    flash(f'Student {name} deleted successfully!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/scores/entry', methods=['GET', 'POST'])
@login_required
def score_entry():
    current_term = get_current_term()
    
    if not current_term:
        flash('No active term found. Please create a term first.', 'warning')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        student_id = request.form.get('student_id')
        subject_id = request.form.get('subject_id')
        ca1 = float(request.form.get('ca1', 0))
        ca2 = float(request.form.get('ca2', 0))
        exam = float(request.form.get('exam', 0))
        remark = request.form.get('remark', '')
        
        existing = Score.query.filter_by(
            student_id=student_id,
            subject_id=subject_id,
            term_id=current_term.id
        ).first()
        
        if existing:
            existing.ca1 = ca1
            existing.ca2 = ca2
            existing.exam = exam
            existing.teacher_remark = remark
            existing.calculate_total()
        else:
            score = Score(
                student_id=student_id,
                subject_id=subject_id,
                term_id=current_term.id,
                ca1=ca1,
                ca2=ca2,
                exam=exam,
                teacher_remark=remark
            )
            score.calculate_total()
            db.session.add(score)
        
        db.session.commit()
        flash('Score saved successfully!', 'success')
        return redirect(url_for('score_entry'))
    
    students = Student.query.order_by(Student.name).all()
    subjects = Subject.query.order_by(Subject.name).all()
    
    return render_template('score_entry.html', 
                         students=students, 
                         subjects=subjects,
                         current_term=current_term)


@app.route('/report/<int:student_id>')
@login_required
def student_report(student_id):
    student = Student.query.get_or_404(student_id)
    current_term = get_current_term()
    
    if not current_term:
        flash('No active term found.', 'warning')
        return redirect(url_for('dashboard'))
    
    scores = Score.query.filter_by(
        student_id=student_id,
        term_id=current_term.id
    ).all()
    
    class_stats = calculate_class_statistics(student.student_class, current_term.id)
    student_stats = class_stats.get(student_id, {})
    
    report_data = []
    for score in scores:
        class_scores = Score.query.join(Student).filter(
            Student.student_class == student.student_class,
            Score.subject_id == score.subject_id,
            Score.term_id == current_term.id
        ).all()
        
        totals = [s.total for s in class_scores]
        highest = max(totals) if totals else 0
        average = statistics.mean(totals) if totals else 0
        position = sorted(totals, reverse=True).index(score.total) + 1 if score.total in totals else '-'
        
        report_data.append({
            'subject': score.subject.name,
            'ca1': score.ca1,
            'ca2': score.ca2,
            'exam': score.exam,
            'total': score.total,
            'grade': score.grade,
            'remark': score.teacher_remark or '',
            'position': position,
            'class_highest': highest,
            'class_average': round(average, 2)
        })
    
    return render_template('report.html',
                         student=student,
                         report_data=report_data,
                         student_stats=student_stats,
                         current_term=current_term,
                         total_students=len(class_stats))


@app.route('/class-summary')
@app.route('/class_summary')
@login_required
def class_summary():
    current_term = get_current_term()
    
    if not current_term:
        flash('No active term found.', 'warning')
        return redirect(url_for('dashboard'))
    
    classes = db.session.query(Student.student_class).distinct().all()
    
    summary_data = {}
    for (class_name,) in classes:
        stats = calculate_class_statistics(class_name, current_term.id)
        sorted_students = sorted(stats.items(), key=lambda x: x[1]['total'], reverse=True)[:3]
        
        summary_data[class_name] = {
            'total_students': len(stats),
            'top_students': [(stats[sid]['name'], stats[sid]['total']) for sid, _ in sorted_students],
            'class_average': statistics.mean([s['average'] for s in stats.values()]) if stats else 0
        }
    
    return render_template('class_summary.html',
                         summary_data=summary_data,
                         current_term=current_term)


@app.route('/subjects', methods=['GET', 'POST'])
@login_required
def manage_subjects():
    if request.method == 'POST':
        name = request.form.get('name')
        code = request.form.get('code', '')
        
        existing = Subject.query.filter_by(name=name).first()
        if existing:
            flash('Subject already exists!', 'error')
        else:
            subject = Subject(name=name, code=code)
            db.session.add(subject)
            db.session.commit()
            flash('Subject added successfully!', 'success')
        
        return redirect(url_for('manage_subjects'))
    
    subjects = Subject.query.order_by(Subject.name).all()
    return render_template('subjects.html', subjects=subjects)


@app.route('/terms', methods=['GET', 'POST'])
@login_required
def manage_terms():
    if request.method == 'POST':
        name = request.form.get('name')
        academic_year = request.form.get('academic_year')
        is_current = request.form.get('is_current') == 'on'
        
        if is_current:
            Term.query.update({Term.is_current: False})
        
        term = Term(name=name, academic_year=academic_year, is_current=is_current)
        db.session.add(term)
        db.session.commit()
        flash('Term added successfully!', 'success')
        
        return redirect(url_for('manage_terms'))
    
    terms = Term.query.order_by(Term.id.desc()).all()
    return render_template('terms.html', terms=terms)


# For local development
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)