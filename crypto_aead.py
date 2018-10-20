#!/usr/bin/python
import pysodium

# chacha20 with poly1305 in aead mode

def encrypt_aead(key,pt):
    nonce = pysodium.randombytes(12)
    ad = ""
    cipher = pysodium.crypto_aead_chacha20poly1305_encrypt(pt, ad, nonce, key)
    print "Chacha20 Poly1305: Plaintext Len: " + str(len(pt)) + " Cipher Len: " + str(len(cipher))
    return nonce + cipher

def decrypt_aead(key,ct):
    nonce = ct[:12]
    cipher = ct[12:]
    ad = ""
    plaintext = pysodium.crypto_aead_chacha20poly1305_decrypt(cipher, ad, nonce, key)
    return plaintext


def simpleTest():
        key = "AAAAAAAAaaaaaaaaAAAAAAAAaaaaaaaa"
        input_ = "ItsNotATumor"

        print "Key:", key, "(", len(key), " bytes)"
        print "Input:", input_, " (", len(input_), " bytes)"

        nonce = pysodium.randombytes(12)
        ad = "1234"
        print "Nonce:", nonce, "(", len(nonce), " bytes)"
        print "Additional Data: ", ad, " (", len(ad), " bytes)"
        cipher = pysodium.crypto_aead_chacha20poly1305_encrypt(input_, ad, nonce, key)
        print "Cipher:", cipher, " (", len(cipher), " bytes)"
        print "Network Packet:", cipher, ad, nonce, " (", len(cipher) + len(ad) + len(nonce), " bytes)"

        try:
            plaintext = pysodium.crypto_aead_chacha20poly1305_decrypt(cipher, ad, nonce, key)
        except Exception:
            print "Failed to verify"
        else:
            print "Verified and Decrypted."
            print "Plaintext:", plaintext


def twolayers():
        key = "AAAAAAAAaaaaaaaaAAAAAAAAaaaaaaaa"
        input_ = "ItsNotATumor"

        print "Key:", key, "(", len(key), " bytes)"
        print "Input:", input_, " (", len(input_), " bytes)"

        nonce = pysodium.randombytes(12)
        ad = "1234"
        print "Nonce:", nonce, "(", len(nonce), " bytes)"
        print "Additional Data: ", ad, " (", len(ad), " bytes)"
        cipher = pysodium.crypto_aead_chacha20poly1305_encrypt(input_, ad, nonce, key)
        print "Cipher:", cipher, " (", len(cipher), " bytes)"
        print "Cipher1:", cipher, ad, nonce, " (", len(cipher) + len(ad) + len(nonce), " bytes)"
        
        key2 = "BBBBBBBBbbbbbbbbBBBBBBBBbbbbbbbb"
        nonce2 = pysodium.randombytes(12)
        cipher2 = pysodium.crypto_aead_chacha20poly1305_encrypt(cipher, ad, nonce2, key2)
        print "Ciper2:", cipher2, " (", len(cipher2), " bytes)"

        try:
            cipher1 = pysodium.crypto_aead_chacha20poly1305_decrypt(cipher2, ad, nonce2, key2)
        except Exception:
            print "Failed to verify outer layer."
        else:
            print "Verified and Decrypted Outer Layer."
            try:
                plaintext = pysodium.crypto_aead_chacha20poly1305_decrypt(cipher1, ad, nonce, key)
            except Exception:
                print "Failed to verify inner layer."
            else:
                print "Plaintext: ", plaintext


if __name__ == "__main__":
    twolayers()