from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import text  # 添加 text 支持

# 创建临时应用实例
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forklift.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 定义模型（修复字段名冲突问题）
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    points = db.Column(db.Integer, default=100)  # 注册赠送100分
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    price = db.Column(db.Integer, nullable=False)  # 阅读价格（≥100分）
    status = db.Column(db.String(20), default='pending')  # pending/approved/rejected
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    read_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.relationship('User', backref=db.backref('documents', lazy=True))

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'))
    amount = db.Column(db.Integer, nullable=False)
    transaction_type = db.Column(db.String(20))  # read/reward/fee (避免使用type关键字)
    description = db.Column(db.String(100))  # 交易描述
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('transactions', lazy=True))

# 评论模型（修复字段名冲突）
class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False, default='')  # 添加默认值
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # 评论类型：comment-普通评论，like-点赞，dislike-差评（避免使用type关键字）
    comment_type = db.Column(db.String(20), default='comment')
    
    user = db.relationship('User', backref=db.backref('comments', lazy=True))
    document = db.relationship('Document', backref=db.backref('comments', lazy=True))

# 社区动态模型（新增）
class CommunityPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('community_posts', lazy=True))

# 系统统计表
class SystemStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    total_points_created = db.Column(db.Integer, default=0)  # 系统创建的总积分
    total_fees_collected = db.Column(db.Integer, default=0)  # 收取的总手续费
    total_rewards_given = db.Column(db.Integer, default=0)  # 发放的总奖励

# 需求模型
class Demand(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    demand_type = db.Column(db.String(20))  # service/parts
    points_required = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='active')  # active/completed
    contact_info = db.Column(db.String(100))
    
    user = db.relationship('User', backref=db.backref('demands', lazy=True))

def initialize_database():
    with app.app_context():
        # 创建所有表
        db.create_all()
        
        # 初始化系统统计
        if not SystemStats.query.first():
            db.session.add(SystemStats())
            db.session.commit()
            print("系统统计表已初始化")
        
        # 创建管理员账户和测试用户
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', password='admin123', points=500)
            user1 = User(username='user1', password='user123', points=300)
            db.session.add_all([admin, user1])
            db.session.commit()
            print("管理员账号和测试用户已创建")
        
        # 添加测试文档
        if Document.query.count() == 0:
            admin = User.query.filter_by(username='admin').first()
            doc1 = Document(
                title='叉车液压系统维修指南',
                content='详细维修步骤...',
                price=150,
                author_id=admin.id,
                status='approved'
            )
            doc2 = Document(
                title='电动叉车电池维护技巧',
                content='电池保养方法...',
                price=120,
                author_id=admin.id,
                status='approved'
            )
            db.session.add_all([doc1, doc2])
            db.session.commit()
            print("测试文档已添加")
        
        # 添加测试评论
        if Comment.query.count() == 0:
            admin = User.query.filter_by(username='admin').first()
            user1 = User.query.filter_by(username='user1').first()
            doc = Document.query.first()
            
            comment1 = Comment(
                content='非常实用的指南！',
                document_id=doc.id,
                user_id=user1.id,
                comment_type='comment'
            )
            like = Comment(
                content='',  # 显式设置空字符串
                document_id=doc.id,
                user_id=user1.id,
                comment_type='like'
            )
            db.session.add_all([comment1, like])
            db.session.commit()
            print("测试评论已添加")
        
        print("数据库初始化完成！")

if __name__ == '__main__':
    initialize_database()