from werkzeug.security import generate_password_hash
from .service import transaction, now, audit


def seed(db):
    if db.execute('SELECT count(*) FROM users').fetchone()[0]:
        raise RuntimeError('Refusing to seed a nonempty database. Use a new database path for a fresh demo.')
    password = generate_password_hash('Pilot-demo-2026!')
    with transaction(db):
        timestamp = now(db)
        terms = ('DRAFT for Mongolian legal review. Synthetic demo inventory only. Inspect the description and condition before bidding. '
                 'Starting price is the minimum acceptable sale price. Seller handles ownership, item claims, fulfillment and remedies. '
                 'Contact the seller for a condition dispute; report concerns to the operator through the listing. No real-money transactions in this preview.')
        instructions = 'DEMO ONLY — do not transfer money. In an approved pilot, contact the seller to arrange direct payment and pickup. No bank account is configured.'
        for sid, slug, name, address in [(1,'altan-studio','Altan Studio','Demo address · Sukhbaatar district, Ulaanbaatar'),(2,'nomad-objects','Nomad Objects','Demo address · Khan-Uul district, Ulaanbaatar')]:
            db.execute('INSERT INTO shops(id,slug,name,address,contact,terms,instructions,identity_note) VALUES(?,?,?,?,?,?,?,?)',
                       (sid,slug,name,address,slug+'@example.test',terms,instructions,'Synthetic seller record. No real identity review or item authentication has been performed.'))
        for uid, email, alias, role, shop in [(1,'buyer@example.test','Bidder-7F2A','buyer',None),(2,'seller@example.test','Altan-seller','seller',1),
                                           (3,'operator@example.test','Pilot-operator','operator',None),(4,'other-seller@example.test','Nomad-seller','seller',2),
                                           (5,'buyer2@example.test','Bidder-3B91','buyer',None)]:
            db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,0,?)',(uid,email,password,alias,role,shop,timestamp))
        lots = [
            (1,1,'Hammered gold-tone pendant','Oval pendant with a hammered finish on a linked chain.','Demo: light surface marks. Chain included.','Seller statement: gold-tone base metal. No certificate or independent inspection.','pendant',180000,10000,timestamp+3600*6,'open'),
            (2,1,'Steel dress watch','Round steel case, ivory dial and brown leather strap.','Demo: used, with wear to the case and strap. Service history unknown.','Seller statement only. No manufacturer authentication or independent condition report.','watch',240000,20000,timestamp+3600*24,'open'),
            (3,2,'Sculpted silver-tone band','Wide band with an asymmetric curved profile.','Demo: minor marks. Confirm size with the seller.','The metal description is a seller claim. No hallmark test or certificate.','ring',90000,5000,timestamp+3600*36,'open'),
            (4,1,'Archive pendant','A completed synthetic auction with a recorded winner.','Demo only.','No inspection or authentication.','pendant',100000,10000,timestamp-3600,'closed'),
        ]
        for aid,sid,title,description,condition,evidence,image,start,increment,close,state in lots:
            db.execute('''INSERT INTO auctions(id,shop_id,title,description,condition,evidence,image,start_price,increment,closes_at,
                 seller_terms,payment_instructions,state,winner_id,closed_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                 (aid,sid,title,description,condition,evidence,image,start,increment,close,terms,instructions,state,1 if aid==4 else None,close if aid==4 else None,timestamp-7200))
        db.execute('INSERT INTO bids(auction_id,user_id,amount,created_at,request_key) VALUES(4,1,100000,?,?)',(timestamp-4000,'synthetic-seed-award-0001'))
        audit(db,None,'synthetic_seed','system',None,'Two imaginary shops; five demo users; four synthetic listings. Seed award is synthetic, not a real sale.')
