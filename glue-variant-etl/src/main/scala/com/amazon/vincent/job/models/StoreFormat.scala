// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models

sealed trait StoreFormat {
  def name: String
}

object StoreFormat {
  case object TSV extends StoreFormat {
    override val name: String = "TSV"
  }

  case object GFF extends StoreFormat {
    override val name: String = "GFF"
  }

  case object VCF extends StoreFormat {
    override val name: String = "VCF"
  }

  val values = Seq(TSV, GFF, VCF)

  def withName(name: String): StoreFormat = {
    values.find(value => value.name.equals(name)) match {
      case Some(value) => value
      case None => throw new IllegalArgumentException(s"Unsupported StoreFormat: $name")
    }
  }
}
