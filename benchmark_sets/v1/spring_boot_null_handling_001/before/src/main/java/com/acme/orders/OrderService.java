package com.acme.orders;

import org.springframework.web.server.ResponseStatusException;
import static org.springframework.http.HttpStatus.NOT_FOUND;

class OrderService {
    private OrderRepository repository;

    Order find(long id) {
        return repository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(NOT_FOUND, "Order not found"));
    }
}

