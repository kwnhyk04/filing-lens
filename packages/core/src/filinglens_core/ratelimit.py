"""Token bucket in Redis, shared by every process: one atomic Lua script on Redis's clock."""

# KEYS[1]: the bucket, a hash of tokens and the time they were counted (ms).
# KEYS[2], optional: a cool-off key that pauses the bucket while it exists.
# ARGV: tokens added per second, capacity.
# Returns {1, whole tokens left} when it took a token, otherwise {0, ms until one is free}.
BUCKET_SCRIPT = """
local rate, capacity = tonumber(ARGV[1]), tonumber(ARGV[2])
if KEYS[2] then
  local paused = redis.call('PTTL', KEYS[2])
  if paused > 0 then return {0, paused} end
end
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local state = redis.call('HMGET', KEYS[1], 'tokens', 'at')
local tokens = tonumber(state[1]) or capacity
local at = tonumber(state[2]) or now
tokens = math.min(capacity, tokens + math.max(0, now - at) * rate / 1000)
local taken = tokens >= 1
if taken then tokens = tokens - 1 end
redis.call('HSET', KEYS[1], 'tokens', tostring(tokens), 'at', tostring(now))
redis.call('PEXPIRE', KEYS[1], math.ceil(capacity / rate * 1000) + 1000)
if taken then return {1, math.floor(tokens)} end
return {0, math.ceil((1 - tokens) * 1000 / rate)}
"""
