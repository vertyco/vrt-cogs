from urllib.parse import urlparse
url = 'http://images-eds.xboxlive.com/image?url=MSVnmBUo_fHjbLYMjAEUQ7jpZDVN2u6Zk9G1CFEaF7foyeb9vHXW1jCDjRAUQwSfSixddYmsZG3hy.4pWL6lo75K5CCB.0hyfS0ibnpVh65V43OyYbHwrazgV7Byuhzlxyd1VwsADeFD17KtkUqiAjfTwfcgNI6YDB9BmT_UDULqXYT2ZyNEhWf4L.8ehsr7z.JBbW.iqxbStWJvcf2.UhF4fojkUXPTPMPdTjrDx5RDsFm7y7YiGDDR_whmc5OY.9hVVFuT_9mXrhXEOCHcYram65nQ_V2k4VsH.2agCtc-'

u = urlparse(url)
print(u)
url = f"{u[0]}://{u[1]}{u[2].lower()}"
print(url)
# Prints url without the query