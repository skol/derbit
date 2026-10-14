from sqlalchemy import MetaData, Table, Column, Integer, String, Numeric, BigInteger, Index

metadata = MetaData()

prices = Table("prices", metadata,
               Column("id", Integer, primary_key=True, autoincrement=True),
               Column("ticker", String, nullable=False),
               Column("price", Numeric(20, 8), nullable=False),
               Column("timestamp", BigInteger, nullable=False),

               Index('idx_prices_ticker_timestamp', 'ticker', Column('timestamp').desc(), unique=True),
               )
