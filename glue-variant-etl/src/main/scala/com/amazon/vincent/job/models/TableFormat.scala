// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models

object TableFormat extends Enumeration {
  val HIVE_0: TableFormat.Value = Value(1, "hive_0")
  val ICEBERG_0: TableFormat.Value = Value(2, "iceberg_0")
  val ICEBERG_1: TableFormat.Value = Value(3, "iceberg_1")

  def supportsImportDataValidation(version: Int): Boolean = {
    version > 1
  }

  def supportsVEPParsing(version: Int): Boolean = {
    version > 2
  }

  def version(string: String): Int = {
    try {
      TableFormat.withName(string).id
    } catch {
      case e: NoSuchElementException =>
        println(s"Could not find version with $string")
        -1
    }
  }
}
