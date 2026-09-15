/**
 * @file ring_buffer.h
 * @brief In-memory store-and-forward telemetry ring buffer for network dropout resilience.
 *
 * Provides a statically-allocated circular FIFO buffer for Telemetry snapshots.
 * When the network (Wi-Fi / REST / MQTT) is unreachable, outgoing telemetry records
 * are enqueued in RAM. Once connection is restored, records are drained in chronological
 * order to preserve continuous time-series history.
 *
 * Policy on overflow: Overwrite oldest record to ensure the most recent operational
 * telemetry and trends are always preserved, while tracking total dropped samples.
 */

#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace ems {

template <typename T, size_t Capacity>
class RingBuffer {
    static_assert(Capacity > 0, "RingBuffer capacity must be greater than zero");

public:
    RingBuffer() : head_(0), tail_(0), count_(0), overflow_count_(0) {}

    /**
     * @brief Push an item into the buffer.
     * If the buffer is full, the oldest item is overwritten and overflow count is incremented.
     * @param item Item to insert
     * @return true if inserted without dropping; false if an older record was overwritten
     */
    bool push(const T& item) {
        bool overwritten = false;
        if (isFull()) {
            // Overwrite oldest item: advance tail
            tail_ = (tail_ + 1) % Capacity;
            count_--;
            overflow_count_++;
            overwritten = true;
        }

        buffer_[head_] = item;
        head_ = (head_ + 1) % Capacity;
        count_++;

        return !overwritten;
    }

    /**
     * @brief Pop the oldest item from the buffer (FIFO).
     * @param[out] item Destination to store popped item
     * @return true if item was retrieved, false if buffer is empty
     */
    bool pop(T& item) {
        if (isEmpty()) {
            return false;
        }

        item = buffer_[tail_];
        tail_ = (tail_ + 1) % Capacity;
        count_--;
        return true;
    }

    /**
     * @brief Peek at the oldest item without removing it.
     * @param[out] item Destination to store peeked item
     * @return true if item exists, false if buffer is empty
     */
    bool peek(T& item) const {
        if (isEmpty()) {
            return false;
        }
        item = buffer_[tail_];
        return true;
    }

    /**
     * @brief Check if buffer is empty.
     */
    bool isEmpty() const {
        return count_ == 0;
    }

    /**
     * @brief Check if buffer is full.
     */
    bool isFull() const {
        return count_ == Capacity;
    }

    /**
     * @brief Current number of items stored in buffer.
     */
    size_t size() const {
        return count_;
    }

    /**
     * @brief Maximum capacity of buffer.
     */
    constexpr size_t capacity() const {
        return Capacity;
    }

    /**
     * @brief Total number of dropped records due to overflow.
     */
    uint32_t overflowCount() const {
        return overflow_count_;
    }

    /**
     * @brief Clear all elements from buffer.
     */
    void clear() {
        head_ = 0;
        tail_ = 0;
        count_ = 0;
    }

    /**
     * @brief Reset overflow counter.
     */
    void resetOverflowCount() {
        overflow_count_ = 0;
    }

private:
    T buffer_[Capacity];
    size_t head_;
    size_t tail_;
    size_t count_;
    uint32_t overflow_count_;
};

} // namespace ems
