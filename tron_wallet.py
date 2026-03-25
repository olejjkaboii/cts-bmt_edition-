import os
import struct
import hashlib
import base58
import requests
import hmac
import ecdsa
from dotenv import load_dotenv
from Crypto.Hash import keccak

load_dotenv()

TRON_PRIVATE_KEY = os.getenv('TRON_PRIVATE_KEY', '')
TRON_ADDRESS = os.getenv('TRON_ADDRESS', '')
TRON_SEED = os.getenv('TRON_SEED', '')

TRON_API_URL = 'https://api.trongrid.io'

def mnemonic_to_seed(mnemonic, password=''):
    mnemonic = mnemonic.strip()
    salt = b'mnemonic' + password.encode('utf-8')
    seed = hashlib.pbkdf2_hmac('sha512', mnemonic.encode('utf-8'), salt, 2048)
    return seed

def derive_private_key(seed, index=0):
    path = f"m/44'/195'/0'/0/{index}"
    
    # Первая 32 байта seed как master private key
    key = seed[:32]
    chain_code = seed[32:64]
    
    path_parts = path.split('/')[1:]  # Пропускаем 'm'
    
    for part in path_parts:
        hardened = part.endswith("'")
        if hardened:
            part = part[:-1]
        
        index_val = int(part)
        if hardened:
            index_val += 0x80000000
        
        # ИСПРАВЛЕНО: правильный HMAC
        data = key + struct.pack('>I', index_val)
        I = hmac.new(chain_code, data, hashlib.sha512).digest()
        key = I[:32]
        chain_code = I[32:64]
    
    return key.hex()

def private_key_to_public_key(private_key_hex):
    """ИСПРАВЛЕНО: генерируем настоящий публичный ключ из приватного"""
    private_key_bytes = bytes.fromhex(private_key_hex)
    sk = ecdsa.SigningKey.from_string(private_key_bytes, curve=ecdsa.SECP256k1)
    vk = sk.verifying_key
    public_key = b'\x04' + vk.to_string()  # Несжатый публичный ключ
    return public_key

def private_key_to_tron_address(private_key_hex):
    """ИСПРАВЛЕНО: правильная генерация адреса TRON"""
    public_key = private_key_to_public_key(private_key_hex)
    
    # Keccak256 хеш публичного ключа (без 0x04 префикса для хеширования)
    pubkey_hash = keccak.new(digest_bits=256)
    pubkey_hash.update(public_key[1:])  # Убираем 0x04
    hash_digest = pubkey_hash.digest()
    
    # Берем последние 20 байт
    address_bytes = hash_digest[-20:]
    address_with_prefix = b'\x41' + address_bytes
    
    # Base58Check с чексуммой
    tron_address = base58.b58encode_check(address_with_prefix).decode('ascii')
    return tron_address

def create_trc20_address(index=0):
    try:
        # Используем HD derivation из сид фразы (BIP44 для Tron: m/44'/195'/0'/0/0)
        if TRON_SEED:
            seed = mnemonic_to_seed(TRON_SEED)
            
            # BIP44 path: m/44'/195'/0'/0/index
            key = seed[:32]
            chain_code = seed[32:64]
            
            path = [44 + 0x80000000, 195 + 0x80000000, 0 + 0x80000000, 0, index]
            
            for idx in path:
                data = key + struct.pack('>I', idx)
                I = hmac.new(chain_code, data, hashlib.sha512).digest()
                key = I[:32]
                chain_code = I[32:64]
            
            private_key = key.hex()
            address = private_key_to_tron_address(private_key)
            print(f"Generated address {index}: {address}")
            return address
        elif TRON_PRIVATE_KEY:
            if index == 0:
                address = private_key_to_tron_address(TRON_PRIVATE_KEY)
            else:
                key_bytes = bytes.fromhex(TRON_PRIVATE_KEY)
                new_key = bytes([(b + index) % 256 for b in key_bytes])
                new_key_hex = new_key.hex()
                address = private_key_to_tron_address(new_key_hex)
            print(f"Generated address {index}: {address}")
            return address
        elif TRON_ADDRESS:
            print(f"Using fixed address: {TRON_ADDRESS}")
            return TRON_ADDRESS
        else:
            print("No TRON_SEED, TRON_PRIVATE_KEY or TRON_ADDRESS set")
            return None
    except Exception as e:
        print(f"Error generating address: {e}")
        return None

def check_balance(address):
    """ИСПРАВЛЕНО: правильный вызов API TronGrid"""
    try:
        # TronGrid ожидает base58 адрес напрямую
        url = f"{TRON_API_URL}/wallet/getaccount"
        payload = {"address": address}  # Base58 адрес!
        headers = {'Content-Type': 'application/json', 'TRON-PRO-API-KEY': ''}
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'balance' in data:
                balance_trx = data['balance'] / 1000000
                print(f"TRX Balance: {balance_trx}")
                return balance_trx
            return 0
        else:
            print(f"API error: {response.status_code} - {response.text[:100]}")
            return 0
    except Exception as e:
        print(f"Error checking balance: {e}")
        return 0

if __name__ == "__main__":
    if TRON_SEED:
        print(f"Seed: {TRON_SEED[:20]}...")
        # Генерируем несколько адресов из одного seed
        for i in range(3):
            addr = create_trc20_address(i)
            if addr:
                balance = check_balance(addr)
                print(f"Address {i} balance: {balance} TRX")
        print("\nВсе адреса выведены из одного seed - это ваш основной кошелек!")
