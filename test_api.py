import urllib.request
try:
    response = urllib.request.urlopen('http://127.0.0.1:5000/api/stats', timeout=2)
    print(response.read().decode('utf-8'))
except Exception as e:
    print("Error:", e)
