from cryptography.fernet import Fernet
import os

key = Fernet.generate_key()
crypto = Fernet(key)

def encrypt(plain_text):
    if isinstance(plain_text, basestring):
        string_text = str(plain_text)
        return crypto.encrypt(bytes(string_text))
    else:
        raise Exception('Only strings are allowed.')

def decrypt(cipher_text):
    return crypto.decrypt(cipher_text)

print "Key: ", key

#plain = 'HelloWorldHelloWorldHelloWorldHelloWorldHelloWorld'
plain = 'ah'
print 'Plain LEN: ', len(plain)

cypher = encrypt(plain)
print 'Cypher LEN: ', len(cypher)

print decrypt(cypher) 
