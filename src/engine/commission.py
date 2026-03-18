import backtrader as bt

class JapanStockCommission(bt.CommInfoBase):
    """
    Custom Commission model simulating Japanese Stock Trading friction.
    Assumes percentage-based commission.
    """
    params = (
        ('commission', 0.001), # 0.1% default
        ('stocklike', True),
        ('commtype', bt.CommInfoBase.COMM_FIXED),
    )

    def _getcommission(self, size, price, pseudoexec):
        """calculate commission"""
        return abs(size) * price * self.p.commission
