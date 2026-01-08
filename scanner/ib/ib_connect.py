import logging
import os
import random
from typing import List

from ib_insync import IB, ScannerSubscription, Stock

logger = logging.getLogger(__name__)

IB_HOST = os.environ.get("IB_HOST", "127.0.0.1")
IB_PORT = int(os.environ.get("IB_PORT", "7496"))
IB_CONNECT_TIMEOUT = float(os.environ.get("IB_CONNECT_TIMEOUT", "12"))


def ib_connect() -> IB:
    ib = IB()
    ib.RaiseRequestErrors = False
    client_id = random.randint(1000, 9999)
    logger.info("Connecting to %s:%s with clientId %s...", IB_HOST, IB_PORT, client_id)
    ib.connect(IB_HOST, IB_PORT, clientId=client_id, timeout=IB_CONNECT_TIMEOUT)
    return ib


def fetch_top_gainers(ib: IB, n: int = 50) -> List[Stock]:
    sub = ScannerSubscription(
        instrument="STK",
        locationCode="STK.US.MAJOR",
        scanCode="TOP_PERC_GAIN",
        numberOfRows=n,
    )
    scan_data = ib.reqScannerData(sub)
    contracts: List[Stock] = []
    for item in scan_data:
        contract = item.contractDetails.contract
        contracts.append(Stock(contract.symbol, "SMART", "USD"))
    return contracts
